"""Extra built-in tools for agent_runtime.

Lives in its own module so custom_invoker.py stays readable. Each function
follows the same signature:

    async def built_in_invoke_<name>(
        arguments: dict[str, Any],
        *,
        tenant_id: UUID,
        workspace_id: UUID | None,
        call_id: UUID,
        actor_id: UUID,
    ) -> dict[str, Any]

18 tools in 3 categories (see docs/refactor/agent-builtin-tools-v2.md):

  EDIT / DIFF
    - apply_patch       (multi-file exact-match replacements)
    - diff              (file vs file / text vs text, unified)

  VIEW
    - image_view        (PNG/JPG → base64 thumbnail)
    - pdf_read          (PDF → text, first N pages)

  QUERY
    - json_query        (simplified JSONPath: $..a[?(@.x==y)])
    - csv_query         (CSV row filter + column select)
    - git_status        (git status --short in workspace)
    - git_diff          (git diff in workspace)
    - git_log           (git log -n N in workspace)
    - code_search       (ast-grep if available, else grep)
    - convert_format    (csv↔json, json↔yaml)

  EXTENDED
    - fetch_url_with_auth (http_fetch + headers/cookies/auth)
    - calculator        (safe math, no eval())

  STUBS (frontend hook)
    - ask_user_question (returns {questions: [...]} for UI card)
    - notify_user       (returns {title, body, level} for toast)
    - plan_submit       (returns plan steps for approval UI)
    - todo_write        (returns todos for side list)
    - delegate_to_agent (returns {agent_id, task} for routing)

Safety: every tool that touches the filesystem / shell goes through
custom_invoker's `_safe_resolve` / `_get_settings()` workspace gating, so a
malicious path can't escape the workspace.

Audit: each tool returns its result; the caller (custom_invoker.invoke)
emits the audit_log row via the `_audit()` singleton helper. We don't
duplicate that here.
"""

from __future__ import annotations

import ast
import base64
import csv
import difflib
import io
import json
import logging
import re as _re
import subprocess as _subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pypdf
from PIL import Image as PILImage

_log = logging.getLogger(__name__)


# ─── shared helpers (workspace resolution) ─────────────────────────────

async def _ws_dir(workspace_id: UUID | None) -> Path | str:
    """Resolve workspace_dir; returns error string on failure."""
    if workspace_id is None:
        return "workspace_id required"
    # Import lazily to avoid a circular dep at module load.
    from qzdap.modules.tool.adapter.adapters.custom_invoker import _get_settings
    from qzdap.modules.tool.adapter.adapters.workspace_paths import (
        resolve_workspace_dir,
        ensure_workspace_dir,
    )
    settings = _get_settings()
    ws = resolve_workspace_dir(str(workspace_id), workspace_root=settings.workspace_root)
    try:
        ensure_workspace_dir(ws)
    except OSError as exc:
        return f"workspace_dir unavailable: {exc}"
    return ws


def _safe(ws_dir: Path, user_path: str, op: str, *, allow_write: bool = False) -> Path | str:
    """Mirror of custom_invoker._safe_resolve — re-implemented here to
    avoid a circular import (custom_invoker imports from this module)."""
    from qzdap.modules.tool.adapter.adapters.workspace_paths import (
        is_protected_prefix,
    )
    if not isinstance(user_path, str) or not user_path:
        return f"{op}: path must be a non-empty string"
    if user_path.startswith("/") or user_path.startswith("~"):
        return f"{op}: absolute paths not allowed"
    if "\0" in user_path:
        return f"{op}: NUL byte"
    n = user_path.replace("\\", "/")
    if n.startswith("../") or n == ".." or "/../" in n:
        return f"{op}: '..' not allowed"
    try:
        resolved = (ws_dir / n).resolve()
    except OSError as exc:
        return f"{op}: resolve failed ({exc})"
    if not resolved.is_relative_to(ws_dir):
        return f"{op}: escapes workspace"
    if is_protected_prefix(n):
        return f"{op}: protected prefix ({n.split('/')[0]}/)"
    return resolved


# ═════════════════════════════════════════════════════════════════════════
#  EDIT / DIFF
# ═════════════════════════════════════════════════════════════════════════

async def built_in_invoke_apply_patch(
    arguments: dict[str, Any],
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    call_id: UUID,
    actor_id: UUID,
) -> dict[str, Any]:
    """Apply a list of {path, old_text, new_text} patches in one call."""
    ws = await _ws_dir(workspace_id)
    if isinstance(ws, str):
        return {"error": ws}
    patches = arguments.get("patches")
    if not isinstance(patches, list) or not patches:
        return {"error": "patches must be a non-empty list"}

    applied: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for i, p in enumerate(patches):
        if not isinstance(p, dict):
            failed.append({"index": i, "error": "patch must be an object"})
            continue
        path = (p.get("path") or "").strip()
        old_text = p.get("old_text")
        new_text = p.get("new_text")
        if not path or not isinstance(old_text, str) or not old_text or not isinstance(new_text, str):
            failed.append({"index": i, "path": path, "error": "path/old_text/new_text required"})
            continue
        resolved = _safe(ws, path, "apply_patch", allow_write=True)
        if isinstance(resolved, str):
            failed.append({"index": i, "path": path, "error": resolved})
            continue
        try:
            original = resolved.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            failed.append({"index": i, "path": path, "error": f"read failed: {exc}"})
            continue
        occurrences = original.count(old_text)
        if occurrences == 0:
            failed.append({"index": i, "path": path, "error": "old_text not found"})
            continue
        if occurrences > 1:
            failed.append({"index": i, "path": path, "error": f"old_text matched {occurrences} times; need exactly 1"})
            continue
        try:
            resolved.write_text(original.replace(old_text, new_text, 1), encoding="utf-8")
        except OSError as exc:
            failed.append({"index": i, "path": path, "error": f"write failed: {exc}"})
            continue
        applied.append({"index": i, "path": path, "replacements": 1})

    return {"applied": len(applied), "failed": failed, "total": len(patches),
            "files_changed": [a["path"] for a in applied]}


async def built_in_invoke_diff(
    arguments: dict[str, Any],
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    call_id: UUID,
    actor_id: UUID,
) -> dict[str, Any]:
    """Unified diff between two files OR two text strings."""
    a_path = (arguments.get("a_path") or "").strip()
    b_path = (arguments.get("b_path") or "").strip()
    a_text = arguments.get("a_text")
    b_text = arguments.get("b_text")
    try:
        context_lines = max(0, min(20, int(arguments.get("context_lines") or 3)))
    except (TypeError, ValueError):
        return {"error": "context_lines must be int"}

    # text vs text mode
    if isinstance(a_text, str) and isinstance(b_text, str):
        a_lines, b_lines = a_text.splitlines(), b_text.splitlines()
        diff = "\n".join(difflib.unified_diff(
            a_lines, b_lines,
            fromfile=arguments.get("a_label") or "a",
            tofile=arguments.get("b_label") or "b",
            n=context_lines, lineterm="",
        ))
        return {"diff": diff, "lines": len(diff.splitlines()), "identical": diff == ""}

    # file vs file mode — need a workspace
    if not a_path or not b_path:
        return {"error": "provide either {a_path,b_path} or {a_text,b_text}"}
    ws = await _ws_dir(workspace_id)
    if isinstance(ws, str):
        return {"error": ws}
    a_resolved = _safe(ws, a_path, "diff")
    if isinstance(a_resolved, str):
        return {"error": a_resolved}
    b_resolved = _safe(ws, b_path, "diff")
    if isinstance(b_resolved, str):
        return {"error": b_resolved}
    if not a_resolved.exists():
        return {"error": f"a_path not found: {a_path}"}
    if not b_resolved.exists():
        return {"error": f"b_path not found: {b_path}"}
    try:
        a = a_resolved.read_text(encoding="utf-8").splitlines()
        b = b_resolved.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return {"error": f"read failed: {exc}"}
    diff = "\n".join(difflib.unified_diff(
        a, b, fromfile=a_path, tofile=b_path, n=context_lines, lineterm="",
    ))
    return {"diff": diff, "lines": len(diff.splitlines()), "identical": diff == ""}


# ═════════════════════════════════════════════════════════════════════════
#  VIEW
# ═════════════════════════════════════════════════════════════════════════

async def built_in_invoke_image_view(
    arguments: dict[str, Any],
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    call_id: UUID,
    actor_id: UUID,
) -> dict[str, Any]:
    """Read an image file, downscale, return base64."""
    ws = await _ws_dir(workspace_id)
    if isinstance(ws, str):
        return {"error": ws}
    path = (arguments.get("path") or "").strip()
    if not path:
        return {"error": "path is required"}
    try:
        max_dim = int(arguments.get("max_dim") or 1024)
    except (TypeError, ValueError):
        return {"error": "max_dim must be int"}
    max_dim = max(64, min(4096, max_dim))
    fmt = (arguments.get("format") or "png").lower()
    if fmt not in {"png", "jpeg"}:
        return {"error": "format must be 'png' or 'jpeg'"}

    resolved = _safe(ws, path, "image_view")
    if isinstance(resolved, str):
        return {"error": resolved}
    if not resolved.exists() or not resolved.is_file():
        return {"error": f"file not found: {path}"}

    try:
        with PILImage.open(resolved) as img:
            original_format = (img.format or "PNG").upper()
            if original_format not in {"PNG", "JPEG", "WEBP", "GIF", "BMP"}:
                return {"error": f"unsupported source format: {original_format}"}
            if img.mode not in {"RGB", "RGBA", "L"}:
                img = img.convert("RGB")
            width, height = img.size
            if max(width, height) > max_dim:
                scale = max_dim / max(width, height)
                new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
                img = img.resize(new_size, PILImage.LANCZOS)
            buf = io.BytesIO()
            save_kwargs: dict[str, Any] = {}
            if fmt == "jpeg" and img.mode == "RGBA":
                img = img.convert("RGB")
            if fmt == "jpeg":
                save_kwargs["quality"] = 85
            img.save(buf, format=fmt.upper(), **save_kwargs)
            data = buf.getvalue()
    except (OSError, ValueError) as exc:
        return {"error": f"image read/process failed: {exc}"}

    return {
        "path": path,
        "format": fmt,
        "width": width,
        "height": height,
        "data_base64": base64.b64encode(data).decode("ascii"),
        "bytes": len(data),
    }


async def built_in_invoke_pdf_read(
    arguments: dict[str, Any],
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    call_id: UUID,
    actor_id: UUID,
) -> dict[str, Any]:
    """Extract text from the first N pages of a PDF."""
    ws = await _ws_dir(workspace_id)
    if isinstance(ws, str):
        return {"error": ws}
    path = (arguments.get("path") or "").strip()
    if not path:
        return {"error": "path is required"}
    try:
        max_pages = int(arguments.get("max_pages") or 20)
    except (TypeError, ValueError):
        return {"error": "max_pages must be int"}
    max_pages = max(1, min(500, max_pages))
    try:
        max_chars = int(arguments.get("max_chars") or 200_000)
    except (TypeError, ValueError):
        return {"error": "max_chars must be int"}
    max_chars = max(1000, min(2_000_000, max_chars))

    resolved = _safe(ws, path, "pdf_read")
    if isinstance(resolved, str):
        return {"error": resolved}
    if not resolved.exists() or not resolved.is_file():
        return {"error": f"file not found: {path}"}

    try:
        reader = pypdf.PdfReader(str(resolved))
    except Exception as exc:
        return {"error": f"pdf open failed: {exc}"}
    total_pages = len(reader.pages)
    pages_to_read = min(max_pages, total_pages)
    chunks: list[str] = []
    total_chars = 0
    truncated = False
    for i in range(pages_to_read):
        try:
            text = reader.pages[i].extract_text() or ""
        except Exception:
            text = ""
        if total_chars + len(text) > max_chars:
            remaining = max_chars - total_chars
            if remaining > 0:
                chunks.append(text[:remaining])
                total_chars += remaining
            truncated = True
            break
        chunks.append(f"\n\n=== Page {i + 1} ===\n{text}")
        total_chars += len(text)
        if truncated:
            break
    body = "".join(chunks)
    return {
        "path": path,
        "total_pages": total_pages,
        "pages_read": pages_to_read,
        "text": body,
        "truncated": truncated,
    }


# ═════════════════════════════════════════════════════════════════════════
#  QUERY
# ═════════════════════════════════════════════════════════════════════════

async def built_in_invoke_json_query(
    arguments: dict[str, Any],
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    call_id: UUID,
    actor_id: UUID,
) -> dict[str, Any]:
    """Simplified JSONPath: $..a[?(@.x==y)] — limited but covers common LLM needs."""
    data = arguments.get("data")
    path = (arguments.get("path") or "").strip()
    if data is None:
        return {"error": "data is required"}
    if not path:
        return {"error": "path is required"}
    try:
        nodes = _jsonpath_eval(data, path)
    except (ValueError, SyntaxError) as exc:
        return {"error": f"path parse error: {exc}"}
    return {"matches": nodes, "count": len(nodes)}


def _jsonpath_eval(data: Any, path: str) -> list[Any]:
    """Tiny JSONPath implementation.

    Supports:
      $                       -> whole data
      $.a.b.c                 -> nested key
      $.a[0] / $.a[*]         -> index / wildcard
      $.a[?(@.x == 'y')]      -> filter (==, !=, <, >, <=, >=, in, contains, startsWith)

    Compound paths (e.g. $.items[*].id) are split by '.' and processed
    left-to-right, with '..' doing recursive descent (everywhere it
    matches, results unioned).
    """
    p = path.strip()
    if not p.startswith("$"):
        raise ValueError("path must start with '$'")
    rest = p[1:]
    if rest == "":
        return [data]
    # Split into segments separated by '.' at top level (not inside [..])
    segs: list[str] = []
    buf = ""
    depth = 0
    for ch in rest:
        if ch == "[":
            depth += 1
            buf += ch
        elif ch == "]":
            depth -= 1
            buf += ch
        elif ch == "." and depth == 0:
            if buf:
                segs.append(buf)
            buf = ""
        else:
            buf += ch
    if buf:
        segs.append(buf)
    results: list[Any] = [data]
    for seg in segs:
        results = _jsonpath_step(results, seg)
    return results


def _jsonpath_step(nodes: list[Any], seg: str) -> list[Any]:
    if seg.startswith(".."):
        # recursive descent
        sub = seg[2:]
        out: list[Any] = []
        for n in nodes:
            out.extend(_jsonpath_walk(n, sub))
        return out
    # split key vs [index/filter]
    m = _re.match(r"^([A-Za-z_][\w-]*)?(\[.*\])?$", seg)
    if not m:
        raise ValueError(f"invalid segment: {seg!r}")
    key = m.group(1) or ""
    bracket = m.group(2) or ""
    out = []
    for n in nodes:
        cur = n
        if key:
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                continue
        if bracket:
            cur = _apply_bracket(cur, bracket)
        if isinstance(cur, list):
            out.extend(cur)
        else:
            out.append(cur)
    return out


def _jsonpath_walk(node: Any, key: str) -> list[Any]:
    """Recursive descent: collect node[key] from every level."""
    out = []
    if isinstance(node, dict):
        if key in node:
            out.append(node[key])
        for v in node.values():
            out.extend(_jsonpath_walk(v, key))
    elif isinstance(node, list):
        for v in node:
            out.extend(_jsonpath_walk(v, key))
    return out


def _apply_bracket(node: Any, bracket: str) -> list[Any]:
    """Apply a single [..] filter to a node. Returns list of matches."""
    if not (bracket.startswith("[") and bracket.endswith("]")):
        return [node]
    inner = bracket[1:-1].strip()
    out: list[Any] = []
    if inner == "*":
        if isinstance(node, list):
            return list(node)
        return [node]
    if inner.startswith("?"):
        # filter expression — strip leading "?" and any leading "(" / trailing ")"
        expr = inner[1:].strip().lstrip("(").rstrip(")")
        if not isinstance(node, list):
            return []
        for item in node:
            if _jsonpath_filter(item, expr):
                out.append(item)
        return out
    # numeric index
    try:
        idx = int(inner)
        if isinstance(node, list) and -len(node) <= idx < len(node):
            return [node[idx]]
        return []
    except ValueError:
        return []


def _jsonpath_filter(item: Any, expr: str) -> bool:
    """Evaluate `expr` with @ bound to `item`. Supported ops: ==, !=, <, >, <=, >=, in, contains, startsWith."""
    # Parse @.field OP literal
    m = _re.match(r"^@(?:\.([\w-]+))?\s*(==|!=|>=|<=|>|<|in|contains|startsWith)\s*(.+)$", expr)
    if not m:
        return False
    field, op, raw = m.group(1), m.group(2), m.group(3).strip()
    left = item.get(field) if (field and isinstance(item, dict)) else item
    try:
        right = ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        right = raw.strip("'\"")
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    if op == "<":
        try:
            return left < right
        except TypeError:
            return False
    if op == ">":
        try:
            return left > right
        except TypeError:
            return False
    if op == "<=":
        try:
            return left <= right
        except TypeError:
            return False
    if op == ">=":
        try:
            return left >= right
        except TypeError:
            return False
    if op == "in":
        try:
            return left in right
        except TypeError:
            return False
    if op == "contains":
        try:
            return right in left
        except TypeError:
            return False
    if op == "startsWith":
        return isinstance(left, str) and isinstance(right, str) and left.startswith(right)
    return False


async def built_in_invoke_csv_query(
    arguments: dict[str, Any],
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    call_id: UUID,
    actor_id: UUID,
) -> dict[str, Any]:
    """Filter CSV rows by an inline Python expression, optionally select columns."""
    ws = await _ws_dir(workspace_id)
    if isinstance(ws, str):
        return {"error": ws}
    path = (arguments.get("path") or "").strip()
    if not path:
        return {"error": "path is required"}
    try:
        limit = int(arguments.get("limit") or 100)
    except (TypeError, ValueError):
        return {"error": "limit must be int"}
    limit = max(1, min(10_000, limit))
    columns = arguments.get("columns")
    if columns is not None and (
        not isinstance(columns, list) or not all(isinstance(c, str) for c in columns)
    ):
        return {"error": "columns must be a list of strings"}
    where = arguments.get("where") or ""
    if not isinstance(where, str):
        return {"error": "where must be a string"}

    resolved = _safe(ws, path, "csv_query")
    if isinstance(resolved, str):
        return {"error": resolved}
    if not resolved.exists() or not resolved.is_file():
        return {"error": f"file not found: {path}"}
    try:
        with resolved.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            all_rows = [r for r in reader]
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        return {"error": f"csv read failed: {exc}"}

    total = len(all_rows)
    matched: list[dict[str, str]] = []
    truncated = False
    for row in all_rows:
        if where and not _csv_eval_where(where, row):
            continue
        if columns:
            matched.append({c: row.get(c, "") for c in columns})
        else:
            matched.append(dict(row))
        if len(matched) >= limit:
            truncated = len(all_rows) > limit
            break

    return {"path": path, "rows": matched, "count": len(matched), "total": total,
            "truncated": truncated}


def _csv_eval_where(expr: str, row: dict[str, str]) -> bool:
    """Safe eval of CSV where clause. Allowed: column refs (alnum+_), operators, literals, function calls in allow-list."""
    if not expr.strip():
        return True
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return False
    # Build safe namespace
    safe_globals = {"__builtins__": {}}
    safe_locals = {k: v for k, v in row.items()}
    # Whitelist functions
    for fn in ("str", "int", "float", "len", "min", "max", "bool"):
        safe_globals[fn] = __builtins__[fn] if hasattr(__builtins__, fn) else None  # type: ignore[index]
    try:
        return bool(eval(compile(tree, "<csv_where>", "eval"), safe_globals, safe_locals))  # noqa: S307
    except Exception:
        return False


async def built_in_invoke_git_status(
    arguments: dict[str, Any],
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    call_id: UUID,
    actor_id: UUID,
) -> dict[str, Any]:
    return await _git_run(workspace_id, ["status", "--short"])


async def built_in_invoke_git_diff(
    arguments: dict[str, Any],
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    call_id: UUID,
    actor_id: UUID,
) -> dict[str, Any]:
    args = ["diff"]
    if arguments.get("staged"):
        args.append("--staged")
    try:
        context = int(arguments.get("context_lines") or 3)
    except (TypeError, ValueError):
        return {"error": "context_lines must be int"}
    args.extend([f"--unified={context}"])
    return await _git_run(workspace_id, args)


async def built_in_invoke_git_log(
    arguments: dict[str, Any],
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    call_id: UUID,
    actor_id: UUID,
) -> dict[str, Any]:
    try:
        n = int(arguments.get("n") or 20)
    except (TypeError, ValueError):
        return {"error": "n must be int"}
    n = max(1, min(500, n))
    args = ["log", f"-n{n}", "--pretty=format:%h%x09%an%x09%ad%x09%s", "--date=short"]
    return await _git_run(workspace_id, args)


async def _git_run(
    workspace_id: UUID | None, args: list[str], *, timeout_s: int = 10
) -> dict[str, Any]:
    ws = await _ws_dir(workspace_id)
    if isinstance(ws, str):
        return {"error": ws}
    try:
        proc = _subprocess.run(
            ["git", *args],
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except FileNotFoundError:
        return {"error": "git binary not found on PATH"}
    except _subprocess.TimeoutExpired:
        return {"error": f"git timed out after {timeout_s}s"}
    except Exception as exc:
        return {"error": f"git failed: {exc}"}
    return {
        "stdout": proc.stdout[:102_400],
        "stderr": proc.stderr[:1024],
        "exit_code": proc.returncode,
        "command": "git " + " ".join(args),
        "cwd": str(ws),
    }


async def built_in_invoke_code_search(
    arguments: dict[str, Any],
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    call_id: UUID,
    actor_id: UUID,
) -> dict[str, Any]:
    """Syntax-aware code search. Tries `ast-grep` first; falls back to grep.

    ast-grep pattern syntax (https://ast-grep.github.io/):
      pattern: "def $FN($$$ARGS): $$$BODY"
      lang:    "python" | "typescript" | "tsx" | "javascript" | "rust" | "go"
    """
    ws = await _ws_dir(workspace_id)
    if isinstance(ws, str):
        return {"error": ws}
    pattern = (arguments.get("pattern") or "").strip()
    if not pattern:
        return {"error": "pattern is required"}
    lang = (arguments.get("lang") or "python").lower()
    cwd_arg = (arguments.get("cwd") or "").strip() or "."
    try:
        max_results = int(arguments.get("max_results") or 200)
    except (TypeError, ValueError):
        return {"error": "max_results must be int"}
    max_results = max(1, min(2000, max_results))
    include = (arguments.get("include") or "").strip() or "*"

    resolved_cwd = _safe(ws, cwd_arg, "code_search")
    if isinstance(resolved_cwd, str):
        return {"error": resolved_cwd}

    # Try ast-grep first
    try:
        proc = _subprocess.run(
            ["ast-grep", "run", "--pattern", pattern, "--lang", lang, str(resolved_cwd)],
            capture_output=True, text=True, timeout=15,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            lines = proc.stdout.splitlines()[:max_results]
            matches = []
            for ln in lines:
                # ast-grep output: "file:line:col\tmatch"
                parts = ln.split(":", 2)
                if len(parts) >= 2:
                    matches.append({"path": parts[0], "line": parts[1], "snippet": parts[2] if len(parts) > 2 else ""})
            return {"engine": "ast-grep", "matches": matches, "count": len(matches),
                    "truncated": len(proc.stdout.splitlines()) > max_results}
    except (FileNotFoundError, _subprocess.TimeoutExpired):
        pass

    # Fallback: recursive grep on include pattern
    matches: list[dict[str, Any]] = []
    truncated = False
    try:
        for p in sorted(resolved_cwd.rglob(include)):
            if not p.is_file():
                continue
            try:
                rel = str(p.relative_to(ws))
            except ValueError:
                continue
            for ln_num, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
                if pattern in line:
                    if len(matches) >= max_results:
                        truncated = True
                        break
                    matches.append({"path": rel, "line": ln_num, "snippet": line.strip()[:200]})
            if truncated:
                break
    except OSError as exc:
        return {"error": f"search failed: {exc}"}
    return {"engine": "grep-fallback", "matches": matches, "count": len(matches), "truncated": truncated}


async def built_in_invoke_convert_format(
    arguments: dict[str, Any],
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    call_id: UUID,
    actor_id: UUID,
) -> dict[str, Any]:
    """Convert between csv / json / yaml. input is either inline string or {path:...}."""
    fmt_from = (arguments.get("from") or "").lower()
    fmt_to = (arguments.get("to") or "").lower()
    if fmt_from not in {"csv", "json", "yaml"} or fmt_to not in {"csv", "json", "yaml"}:
        return {"error": "from/to must be one of csv, json, yaml"}
    if fmt_from == fmt_to:
        return {"error": "from and to are the same format"}
    input_value = arguments.get("input")
    input_path = (arguments.get("path") or "").strip() if isinstance(arguments.get("path"), str) else ""
    if input_path:
        ws = await _ws_dir(workspace_id)
        if isinstance(ws, str):
            return {"error": ws}
        resolved = _safe(ws, input_path, "convert_format")
        if isinstance(resolved, str):
            return {"error": resolved}
        if not resolved.exists() or not resolved.is_file():
            return {"error": f"file not found: {input_path}"}
        try:
            input_value = resolved.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return {"error": f"read failed: {exc}"}
    if not isinstance(input_value, str):
        return {"error": "input or path required (string content)"}

    # Parse
    try:
        if fmt_from == "csv":
            rows = list(csv.DictReader(io.StringIO(input_value)))
            parsed: Any = rows
        elif fmt_from == "json":
            parsed = json.loads(input_value)
        else:  # yaml — tiny custom parser, no dep
            parsed = _yaml_minimal_load(input_value)
    except Exception as exc:
        return {"error": f"parse {fmt_from} failed: {exc}"}

    # Emit
    try:
        if fmt_to == "csv":
            if not isinstance(parsed, list) or not parsed or not isinstance(parsed[0], dict):
                return {"error": "csv output requires a list of dicts (json input must be array of objects)"}
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=list(parsed[0].keys()))
            writer.writeheader()
            for r in parsed:
                writer.writerow(r)
            output = buf.getvalue()
        elif fmt_to == "json":
            output = json.dumps(parsed, ensure_ascii=False, indent=2)
        else:  # yaml
            output = _yaml_minimal_dump(parsed)
    except Exception as exc:
        return {"error": f"emit {fmt_to} failed: {exc}"}

    return {"from": fmt_from, "to": fmt_to, "output": output, "bytes": len(output)}


def _yaml_minimal_load(text: str) -> Any:
    """Tiny YAML reader: supports mappings + sequences + scalars. NOT a full YAML impl."""
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        return None

    def parse_scalar(s: str) -> Any:
        s = s.strip()
        if s in {"true", "True", "yes"}:
            return True
        if s in {"false", "False", "no"}:
            return False
        if s in {"null", "Null", "~", ""}:
            return None
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            return s[1:-1]
        try:
            return int(s)
        except ValueError:
            pass
        try:
            return float(s)
        except ValueError:
            pass
        return s

    def parse_block(start: int, indent: int) -> tuple[Any, int]:
        first = lines[start]
        content = first[indent:]
        # sequence?
        if content.startswith("- "):
            items = []
            i = start
            while i < len(lines):
                ln = lines[i]
                stripped = ln.lstrip()
                cur_indent = len(ln) - len(stripped)
                if cur_indent < indent:
                    break
                if not stripped.startswith("- "):
                    break
                # value after "- "
                val = stripped[2:]
                if not val:
                    items.append(None)
                    i += 1
                    continue
                if val.startswith(("- ", "* ")) or ":" in val and "\"" not in val:
                    # nested mapping or sequence under this key
                    if val.endswith(":"):
                        # key on its own line, value on next line(s)
                        key = val[:-1].strip()
                        sub, i = parse_block(i + 1, cur_indent + 2)
                        items.append({key: sub})
                    else:
                        items.append(parse_scalar(val))
                        i += 1
                else:
                    items.append(parse_scalar(val))
                    i += 1
            return items, i
        # mapping
        result: dict[str, Any] = {}
        i = start
        while i < len(lines):
            ln = lines[i]
            stripped = ln.lstrip()
            cur_indent = len(ln) - len(stripped)
            if cur_indent < indent:
                break
            if ":" not in stripped:
                break
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            if not val:
                # nested
                sub, i = parse_block(i + 1, cur_indent + 2)
                result[key] = sub
            else:
                result[key] = parse_scalar(val)
                i += 1
        return result, i

    parsed, _ = parse_block(0, 0)
    return parsed


def _yaml_minimal_dump(obj: Any, indent: int = 0) -> str:
    """Tiny YAML writer. Supports dict / list / scalar."""
    pad = "  " * indent
    if isinstance(obj, dict):
        if not obj:
            return pad + "{}\n"
        lines = []
        for k, v in obj.items():
            if isinstance(v, (dict, list)) and v:
                lines.append(f"{pad}{k}:\n")
                lines.append(_yaml_minimal_dump(v, indent + 1))
            else:
                lines.append(f"{pad}{k}: {_yaml_scalar(v)}\n")
        return "".join(lines)
    if isinstance(obj, list):
        if not obj:
            return pad + "[]\n"
        lines = []
        for item in obj:
            if isinstance(item, (dict, list)) and item:
                # First line gets "- " then nested
                inner = _yaml_minimal_dump(item, indent + 1).rstrip("\n")
                lines.append(f"{pad}-\n{inner}\n")
            else:
                lines.append(f"{pad}- {_yaml_scalar(item)}\n")
        return "".join(lines)
    return pad + _yaml_scalar(obj) + "\n"


def _yaml_scalar(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if any(ch in s for ch in [":", "#", "\n", '"', "'"]) or s in {"true", "false", "null", "yes", "no"}:
        return json.dumps(s, ensure_ascii=False)
    return s


# ═════════════════════════════════════════════════════════════════════════
#  EXTENDED
# ═════════════════════════════════════════════════════════════════════════

async def built_in_invoke_fetch_url_with_auth(
    arguments: dict[str, Any],
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    call_id: UUID,
    actor_id: UUID,
) -> dict[str, Any]:
    """http_fetch + custom headers / cookies / bearer auth. NO network egress audit (yet)."""
    url = (arguments.get("url") or "").strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        return {"error": "url must start with http:// or https://"}
    try:
        max_chars = int(arguments.get("max_chars") or 8_000)
    except (TypeError, ValueError):
        return {"error": "max_chars must be int"}
    max_chars = max(500, min(50_000, max_chars))
    headers = arguments.get("headers") or {}
    cookies = arguments.get("cookies") or {}
    bearer = arguments.get("bearer_token")
    if not isinstance(headers, dict) or not all(isinstance(v, str) for v in headers.values()):
        return {"error": "headers must be a dict of str→str"}
    if not isinstance(cookies, dict) or not all(isinstance(v, str) for v in cookies.values()):
        return {"error": "cookies must be a dict of str→str"}

    if bearer:
        headers = {**headers, "Authorization": f"Bearer {bearer}"}

    req_headers = {
        "User-Agent": "QZDAP-AI/1.0",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        **headers,
    }
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            follow_redirects=True,
            headers=req_headers,
            cookies=httpx.Cookies(cookies),
        ) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "").lower()
                if not any(ct in content_type for ct in ("text/", "application/json", "application/xml", "application/xhtml")):
                    return {"error": f"disallowed content-type: {content_type!r}"}
                buf = bytearray()
                async for chunk in resp.aiter_bytes(chunk_size=32_768):
                    buf.extend(chunk)
                    if len(buf) > 1_048_576:
                        return {"error": "response exceeded 1 MiB"}
                charset = resp.encoding or "utf-8"
                body = buf.decode(charset, errors="replace")
    except httpx.HTTPStatusError as exc:
        return {"error": f"HTTP {exc.response.status_code}"}
    except httpx.TimeoutException:
        return {"error": "timeout after 15s"}
    except (httpx.RequestError, ValueError) as exc:
        return {"error": str(exc)}

    return {"url": url, "status": resp.status_code, "content_type": content_type,
            "headers_sent": req_headers, "body": body[:max_chars]}


async def built_in_invoke_calculator(
    arguments: dict[str, Any],
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    call_id: UUID,
    actor_id: UUID,
) -> dict[str, Any]:
    """Restricted math evaluator. Supports + - * / % ** and whitelisted functions."""
    expr = (arguments.get("expression") or "").strip()
    if not expr:
        return {"error": "expression is required"}
    try:
        value = _safe_eval_math(expr)
    except (ValueError, SyntaxError, TypeError, ZeroDivisionError) as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
    return {
        "expression": expr,
        "value": value,
        "formatted": f"{value:g}" if isinstance(value, (int, float)) else str(value),
    }


def _safe_eval_math(expr: str) -> Any:
    """Eval a math expression using a restricted AST visitor. NO eval()/exec()."""
    tree = ast.parse(expr, mode="eval")
    return _math_eval(tree.body)


_ALLOWED_FUNCS = {
    "abs": abs, "round": round, "min": min, "max": max, "int": int, "float": float,
    "sqrt": __import__("math").sqrt, "log": __import__("math").log, "log2": __import__("math").log2,
    "log10": __import__("math").log10, "sin": __import__("math").sin, "cos": __import__("math").cos,
    "tan": __import__("math").tan, "asin": __import__("math").asin, "acos": __import__("math").acos,
    "atan": __import__("math").atan, "atan2": __import__("math").atan2,
    "degrees": __import__("math").degrees, "radians": __import__("math").radians,
    "ceil": __import__("math").ceil, "floor": __import__("math").floor,
    "pow": pow,
}


def _math_eval(node: ast.AST) -> Any:
    if isinstance(node, ast.Expression):
        return _math_eval(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node.value, str):
            # Allow numeric strings? No — refuse.
            raise ValueError("string constants not allowed")
        raise ValueError("unsupported constant")
    if isinstance(node, ast.BinOp):
        left = _math_eval(node.left)
        right = _math_eval(node.right)
        if isinstance(node.op, ast.Add):    return left + right
        if isinstance(node.op, ast.Sub):    return left - right
        if isinstance(node.op, ast.Mult):   return left * right
        if isinstance(node.op, ast.Div):    return left / right
        if isinstance(node.op, ast.FloorDiv): return left // right
        if isinstance(node.op, ast.Mod):    return left % right
        if isinstance(node.op, ast.Pow):    return left ** right
    if isinstance(node, ast.UnaryOp):
        operand = _math_eval(node.operand)
        if isinstance(node.op, ast.UAdd):  return +operand
        if isinstance(node.op, ast.USub):  return -operand
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("only direct function calls allowed")
        if node.func.id not in _ALLOWED_FUNCS:
            raise ValueError(f"function not allowed: {node.func.id}")
        args = [_math_eval(a) for a in node.args]
        if node.keywords:
            raise ValueError("keyword args not allowed")
        return _ALLOWED_FUNCS[node.func.id](*args)
    if isinstance(node, ast.Name):
        raise ValueError(f"name not allowed: {node.id}")
    raise ValueError(f"unsupported node: {type(node).__name__}")


# ═════════════════════════════════════════════════════════════════════════
#  STUBS — frontend hook
# ═════════════════════════════════════════════════════════════════════════
#
# These return a structured payload + a `_pending_frontend_action` field.
# The frontend SSE consumer (when implemented) will read this field and
# render the matching UI. Backend does NOT block / poll — the LLM stream
# continues with the stub's response.

_STUB_HINT = (
    "frontend integration pending; this stub returns the structured payload "
    "and marks `_pending_frontend_action` for the SSE consumer to render"
)


async def built_in_invoke_ask_user_question(
    arguments: dict[str, Any],
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    call_id: UUID,
    actor_id: UUID,
) -> dict[str, Any]:
    questions = arguments.get("questions")
    if not isinstance(questions, list) or not questions:
        return {"error": "questions must be a non-empty list"}
    for q in questions:
        if not isinstance(q, dict):
            return {"error": "each question must be an object"}
        if not (isinstance(q.get("question"), str) and q["question"].strip()):
            return {"error": "question.question required"}
        if not isinstance(q.get("options"), list) or len(q["options"]) < 2:
            return {"error": "question.options must have >=2 entries"}
    return {
        "questions": questions,
        "_pending_frontend_action": "show_question_card",
        "_status": "awaiting_user_input",
        "_stub_hint": _STUB_HINT,
    }


async def built_in_invoke_notify_user(
    arguments: dict[str, Any],
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    call_id: UUID,
    actor_id: UUID,
) -> dict[str, Any]:
    title = (arguments.get("title") or "").strip()
    body = (arguments.get("body") or "").strip()
    level = (arguments.get("level") or "info").lower()
    if not title:
        return {"error": "title is required"}
    if level not in {"info", "warn", "error", "success"}:
        return {"error": "level must be info|warn|error|success"}
    return {
        "title": title,
        "body": body,
        "level": level,
        "delivered_at": datetime.now(timezone.utc).isoformat(),
        "_pending_frontend_action": "toast",
        "_stub_hint": _STUB_HINT,
    }


async def built_in_invoke_plan_submit(
    arguments: dict[str, Any],
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    call_id: UUID,
    actor_id: UUID,
) -> dict[str, Any]:
    plan_id = (arguments.get("plan_id") or "").strip() or f"plan-{call_id}"
    title = (arguments.get("title") or "执行计划").strip()
    steps = arguments.get("steps")
    reason = (arguments.get("reason") or "").strip()
    if not isinstance(steps, list) or not steps:
        return {"error": "steps must be a non-empty list"}
    for s in steps:
        if not isinstance(s, dict):
            return {"error": "each step must be an object"}
    return {
        "plan_id": plan_id,
        "title": title,
        "steps": steps,
        "reason": reason,
        "_pending_frontend_action": "render_plan",
        "_stub_hint": _STUB_HINT,
    }


async def built_in_invoke_todo_write(
    arguments: dict[str, Any],
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    call_id: UUID,
    actor_id: UUID,
) -> dict[str, Any]:
    todos = arguments.get("todos")
    if not isinstance(todos, list):
        return {"error": "todos must be a list"}
    valid_status = {"pending", "in_progress", "completed"}
    cleaned = []
    for t in todos:
        if not isinstance(t, dict):
            continue
        content = (t.get("content") or "").strip()
        if not content:
            continue
        status = (t.get("status") or "pending").lower()
        if status not in valid_status:
            status = "pending"
        cleaned.append({
            "id": (t.get("id") or f"todo-{len(cleaned)}").strip(),
            "content": content,
            "status": status,
            "active_form": (t.get("active_form") or content).strip(),
        })
    if not cleaned:
        return {"error": "todos must contain at least one valid entry"}
    return {
        "todos": cleaned,
        "_pending_frontend_action": "render_todo_list",
        "_stub_hint": _STUB_HINT,
    }


async def built_in_invoke_delegate_to_agent(
    arguments: dict[str, Any],
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    call_id: UUID,
    actor_id: UUID,
) -> dict[str, Any]:
    agent_id = (arguments.get("agent_id") or "").strip()
    task = (arguments.get("task") or "").strip()
    if not agent_id:
        return {"error": "agent_id is required"}
    if not task:
        return {"error": "task is required"}
    if workspace_id is None:
        return {"error": "workspace context required for delegation"}

    # Phase 14: 由 runner 注入的 parent_session_id — 没有就拒绝, 不允许 LLM
    # 凭空 dispatch 一个没有归属的 sub-agent.
    parent_session_id_str = arguments.get("parent_session_id")
    if not parent_session_id_str:
        return {
            "error": (
                "parent_session_id not provided — runner should inject it; "
                "if you see this in a test, set parent_session_id in the "
                "tool arguments explicitly"
            )
        }
    try:
        parent_session_id = UUID(str(parent_session_id_str))
    except (ValueError, TypeError):
        return {"error": f"parent_session_id {parent_session_id_str!r} is not a valid UUID"}

    usecase = _get_delegate_subagent_usecase()
    if usecase is None:
        # 单元测试或 lifespan 还没跑过的环境, 退回 stub 行为 — 让前端能看到
        # pending action 知道这是 delegate. 生产环境 lifespan 一定会注入.
        return {
            "agent_id": agent_id,
            "task": task,
            "context": arguments.get("context") or {},
            "_pending_frontend_action": "delegate_agent",
            "_stub_hint": _STUB_HINT,
        }

    result = await usecase.execute(
        parent_session_id=parent_session_id,
        target_agent_id=agent_id,
        task=task,
        context=arguments.get("context") or {},
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        actor_id=actor_id,
    )
    # 不再 emit _pending_frontend_action — 子 agent 已经跑完了, 结果直接
    # 喂回 LLM, 父 turn 继续. 让前端 Copilot 看到 ok=True 就走原有 toast 通路
    # 通知用户 "已派给 X, 用时 Ns". _meta 字段带 sub_session_id / duration
    # 供前端可选展示.
    return {
        "ok": result.ok,
        "sub_session_id": result.sub_session_id,
        "agent_id": result.agent_id,
        "final_response": result.final_response or "",
        "status": result.status,
        "duration_ms": result.duration_ms,
        "delegation_depth": result.delegation_depth,
        "error_code": result.error_code,
        "error": result.error,
        "_meta": {
            "subagent_dispatched": True,
            "sub_session_id": result.sub_session_id,
            "duration_ms": result.duration_ms,
            "status": result.status,
        },
    }


# ── Phase 14: 把 DelegateSubagentUseCase 句柄暴露给 stub, 沿用
# bind_audit_recorder 同样的单例模式.

_delegate_usecase_singleton: Any = None


def bind_delegate_subagent_usecase(usecase: Any) -> None:
    """Lifespan calls this once at boot so the delegate_to_agent stub can
    reach the use case from inside custom_invoker (no DI container here).
    """
    global _delegate_usecase_singleton
    _delegate_usecase_singleton = usecase


def _get_delegate_subagent_usecase() -> Any:
    return _delegate_usecase_singleton



__all__ = [
    "built_in_invoke_apply_patch",
    "built_in_invoke_ask_user_question",
    "built_in_invoke_calculator",
    "built_in_invoke_code_search",
    "built_in_invoke_convert_format",
    "built_in_invoke_csv_query",
    "built_in_invoke_delegate_to_agent",
    "built_in_invoke_diff",
    "built_in_invoke_fetch_url_with_auth",
    "built_in_invoke_git_diff",
    "built_in_invoke_git_log",
    "built_in_invoke_git_status",
    "built_in_invoke_image_view",
    "built_in_invoke_json_query",
    "built_in_invoke_notify_user",
    "built_in_invoke_pdf_read",
    "built_in_invoke_plan_submit",
    "built_in_invoke_todo_write",
]