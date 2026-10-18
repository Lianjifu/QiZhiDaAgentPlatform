"""In-process tool registry: tool name → async callable.

Used for the `custom` protocol and for built-in tools registered at
lifespan startup (echo / reverse / clock / web_search / http_fetch).
Wraps the registry as a `CustomInvokerPort` for the use-case layer.

Built-in network tools (web_search / http_fetch) need request context
(tenant_id / workspace_id / call_id / actor_id) for audit-logging and
per-workspace throttling. The registry invokes callables with a kwarg
payload so user-supplied `arguments` stay free of internal routing keys.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

import httpx

from qzdap.modules.tool.adapter.adapters.workspace_paths import (
    ensure_workspace_dir,
    is_protected_prefix,
    resolve_workspace_dir,
)
from qzdap.modules.tool.adapter.adapters.tool_audit import ToolAuditRecorder
from qzdap.modules.tool.domain.errors import ToolNotFound

_log = logging.getLogger(__name__)


class _BuiltinContext(Protocol):
    """Kwargs forwarded to built-in callables alongside `arguments`."""

    tenant_id: UUID
    workspace_id: UUID | None
    call_id: UUID
    actor_id: UUID


class CustomInvokerRegistry:
    def __init__(
        self,
        *,
        workspace_root: str = "/var/qzdap/workspaces",
        default_timeout_seconds: float = 15.0,
        default_max_bytes: int = 1_048_576,
        user_agent: str = "QZDAP-AI/1.0 (+https://qizhida.local)",
        allowed_bash_subdirs: tuple[str, ...] = ("tmp", ".cache"),
    ) -> None:
        self._fns: dict[
            str,
            Callable[..., Awaitable[dict[str, Any]]],
        ] = {}
        self._workspace_root = workspace_root
        self._default_timeout = default_timeout_seconds
        self._default_max_bytes = default_max_bytes
        self._user_agent = user_agent
        self._allowed_bash_subdirs = tuple(allowed_bash_subdirs)

    @property
    def workspace_root(self) -> str:
        return self._workspace_root

    def register(
        self,
        name: str,
        fn: Callable[..., Awaitable[dict[str, Any]]],
    ) -> None:
        if name in self._fns:
            raise ValueError(f"tool {name!r} already registered")
        self._fns[name] = fn

    def unregister(self, name: str) -> None:
        self._fns.pop(name, None)

    def has(self, name: str) -> bool:
        return name in self._fns

    def names(self) -> list[str]:
        return list(self._fns.keys())

    async def invoke(
        self,
        *,
        name: str,
        arguments: dict,
        tenant_id: UUID,
        workspace_id: UUID | None,
        call_id: UUID,
        actor_id: UUID,
    ) -> dict:
        fn = self._fns.get(name)
        if fn is None:
            raise ToolNotFound(f"custom tool {name!r} not registered")
        return dict(
            await fn(
                arguments,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                call_id=call_id,
                actor_id=actor_id,
            )
        )


# ── Built-in tools (registered at lifespan startup) ─────────────────


async def built_in_invoke_echo(arguments: dict[str, Any], **_: Any) -> dict[str, Any]:
    return {"echo": dict(arguments)}


async def built_in_invoke_reverse(arguments: dict[str, Any], **_: Any) -> dict[str, Any]:
    text = arguments.get("text", "")
    if not isinstance(text, str):
        return {"reversed": "", "error": "text must be a string"}
    return {"reversed": text[::-1]}


async def built_in_invoke_clock(arguments: dict[str, Any], **_: Any) -> dict[str, Any]:
    return {"now": datetime.now(UTC).isoformat()}


# ── Network egress built-ins ─────────────────────────────────────────
#
# Both tools run in the qzdap-app process (NOT sandbox). Every egress is
# logged at INFO with tenant_id / workspace_id / call_id so the previous
# ticket's audit pipeline can pick them up later.
#
# Limits (defaults, override via env if needed in a follow-up):
#   - timeout: 15s
#   - max response size: 1 MiB
#   - allowlisted content types: text/html, application/json, text/plain,
#     application/xml, application/xhtml+xml
#   - user agent: identifies as QZDAP-AI


_ALLOWED_CONTENT_TYPES = (
    "text/html",
    "application/xhtml+xml",
    "application/json",
    "application/xml",
    "text/plain",
    "text/xml",
)
_MAX_REDIRECTS = 3


async def _safe_get(
    *,
    url: str,
    timeout: float,
    max_bytes: int,
    user_agent: str,
) -> tuple[int, str, str]:
    """GET with timeout + size cap + content-type allowlist.

    Returns (status_code, content_type, body). Body is bytes-decoded with
    the response's declared charset (fallback utf-8). Raises on timeout,
    non-2xx, oversized body, or disallowed content type.
    """
    timeout_obj = httpx.Timeout(timeout)
    async with httpx.AsyncClient(
        timeout=timeout_obj,
        follow_redirects=True,
        max_redirects=_MAX_REDIRECTS,
        headers={"User-Agent": user_agent, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
    ) as client:
        # Stream so we can stop early on oversize bodies.
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if not any(ct in content_type for ct in _ALLOWED_CONTENT_TYPES):
                raise ValueError(
                    f"disallowed content-type: {content_type!r} "
                    f"(allowed: {', '.join(_ALLOWED_CONTENT_TYPES)})"
                )
            buf = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=32_768):
                buf.extend(chunk)
                if len(buf) > max_bytes:
                    raise ValueError(f"response exceeded {max_bytes} bytes")
            charset = response.encoding or "utf-8"
            return response.status_code, content_type, buf.decode(charset, errors="replace")


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_SCRIPT_RE = re.compile(r"<script\b.*?</script>", re.IGNORECASE | re.DOTALL)
_STYLE_RE = re.compile(r"<style\b.*?</style>", re.IGNORECASE | re.DOTALL)


def _strip_html(html: str, *, max_chars: int) -> str:
    """Crude HTML→text: drop script/style, drop tags, collapse whitespace.

    Not a real HTML parser — but cheap, no extra dep, and good enough for
    feeding LLM context (LLMs don't care about exact formatting)."""
    no_scripts = _SCRIPT_RE.sub(" ", html)
    no_styles = _STYLE_RE.sub(" ", no_scripts)
    no_tags = _TAG_RE.sub(" ", no_styles)
    collapsed = _WS_RE.sub(" ", no_tags).strip()
    if len(collapsed) > max_chars:
        collapsed = collapsed[:max_chars] + "…[truncated]"
    return collapsed


async def built_in_invoke_web_search(
    arguments: dict[str, Any],
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    call_id: UUID,
    actor_id: UUID,
) -> dict[str, Any]:
    """Bing web search (HTML endpoint, no API key). Returns top-N results.

    Args (in `arguments`):
      query: str   — required
      top_k: int   — optional, default 5, max 10

    Returns:
      {query, results: [{title, url, snippet}, ...], source: "bing"}

    Note: Bing's HTML results page is rate-limited per IP and blocks
    obvious bot UAs. We use a desktop Chrome UA + Accept-Language: zh-CN.
    For prod, swap to Tavily/Serper behind an env switch (TODO).
    """
    query = (arguments.get("query") or "").strip()
    if not query:
        return {"error": "query is required", "results": []}
    try:
        top_k = int(arguments.get("top_k") or 5)
    except (TypeError, ValueError):
        return {"error": "top_k must be an integer", "results": []}
    top_k = max(1, min(10, top_k))

    _log.info(
        "tool.network_egress tool=web_search tenant=%s workspace=%s call=%s q=%r",
        tenant_id, workspace_id, call_id, query,
    )

    # Bing HTML search endpoint. q as query param, set lang to zh-Hans.
    try:
        timeout = float(arguments.get("_timeout_seconds") or 15.0)
    except (TypeError, ValueError):
        timeout = 15.0

    url = "https://www.bing.com/search"
    params = {"q": query, "setlang": "zh-Hans"}
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        ) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            html = response.text
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        return {"error": f"web_search upstream unavailable: {exc}", "results": []}

    # Bing HTML extraction:
    #   Each organic result: <li class="b_algo"> ... <h2><a href="URL">TITLE</a></h2> ... <p class="b_paractl">SNIPPET</p>
    #   Captcha / no-result page has <div id="b_content" ...> but no <li class="b_algo">.
    # Use simple regex; good enough for title/url/snippet triplets.
    block_re = re.compile(
        r'<li[^>]+class="b_algo"[^>]*>(.*?)</li>',
        re.IGNORECASE | re.DOTALL,
    )
    title_re = re.compile(
        r'<h2>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    snippet_re = re.compile(
        r'<p[^>]*class="b_lineclamp[^"]*"[^>]*>(.*?)</p>',
        re.IGNORECASE | re.DOTALL,
    )

    results = []
    for block in block_re.findall(html)[:top_k]:
        title_match = title_re.search(block)
        if not title_match:
            continue
        url_clean = title_match.group(1)
        title = _strip_html(title_match.group(2), max_chars=200)
        snippet_match = snippet_re.search(block)
        snippet = (
            _strip_html(snippet_match.group(1), max_chars=400)
            if snippet_match else ""
        )
        results.append({"title": title, "url": url_clean, "snippet": snippet})

    await _audit(
        "tool.network_egress",
        {"tool": "web_search", "url": url, "query": query, "count": len(results)},
        tenant_id=tenant_id, actor_id=actor_id, call_id=call_id,
        workspace_id=workspace_id,
    )
    return {"query": query, "source": "bing", "count": len(results), "results": results}


async def built_in_invoke_http_fetch(
    arguments: dict[str, Any],
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    call_id: UUID,
    actor_id: UUID,
) -> dict[str, Any]:
    """Fetch a URL and return its title + text-only body.

    Args (in `arguments`):
      url: str       — required, must start with http(s)://
      max_chars: int — optional, default 8000, cap body length

    Returns:
      {url, status, content_type, title, body}
    """
    url = (arguments.get("url") or "").strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        return {"error": "url must start with http:// or https://", "url": url}
    try:
        max_chars = int(arguments.get("max_chars") or 8_000)
    except (TypeError, ValueError):
        return {"error": "max_chars must be an integer", "url": url}
    max_chars = max(500, min(50_000, max_chars))

    _log.info(
        "tool.network_egress tool=http_fetch tenant=%s workspace=%s call=%s url=%r",
        tenant_id, workspace_id, call_id, url,
    )

    try:
        status, content_type, body = await _safe_get(
            url=url, timeout=15.0, max_bytes=1_048_576, user_agent="QZDAP-AI/1.0"
        )
    except httpx.HTTPStatusError as exc:
        return {"error": f"HTTP {exc.response.status_code}", "url": url}
    except httpx.TimeoutException:
        return {"error": "timeout after 15s", "url": url}
    except (httpx.RequestError, ValueError) as exc:
        return {"error": str(exc), "url": url}

    title_match = _TITLE_RE.search(body) if content_type.startswith(("text/html", "application/xhtml")) else None
    title = _strip_html(title_match.group(1), max_chars=300) if title_match else ""
    body_text = _strip_html(body, max_chars=max_chars) if "html" in content_type or "xml" in content_type else body[:max_chars]

    await _audit(
        "tool.network_egress",
        {"tool": "http_fetch", "url": url, "status": status, "content_type": content_type},
        tenant_id=tenant_id, actor_id=actor_id, call_id=call_id,
        workspace_id=workspace_id,
    )

    return {
        "url": url,
        "status": status,
        "content_type": content_type,
        "title": title,
        "body": body_text,
    }


__all__ = [
    "CustomInvokerRegistry",
    "built_in_invoke_bash",
    "built_in_invoke_clock",
    "built_in_invoke_edit_file",
    "built_in_invoke_echo",
    "built_in_invoke_glob",
    "built_in_invoke_grep",
    "built_in_invoke_http_fetch",
    "built_in_invoke_ls",
    "built_in_invoke_read_file",
    "built_in_invoke_reverse",
    "built_in_invoke_web_search",
    "built_in_invoke_write_file",
]


# ── File-system / shell built-ins ────────────────────────────────────
#
# Shared helpers (resolve workspace, validate paths, audit log) live here.
# All 7 tools below (bash, read_file, write_file, edit_file, ls, glob, grep)
# use the same _safe_resolve() gate so path-escape and protected-prefix
# checks live in ONE place.
#
# Tools log every invocation via stdlib `logging` at INFO level. Future
# ticket will wire `audit_log` table writes.

import asyncio as _asyncio
import fnmatch as _fnmatch
import re as _re_fs
import subprocess as _subprocess

# Limits (kept conservative; raise in a follow-up if production needs more).
_MAX_BASH_TIMEOUT_S = 300
_DEFAULT_BASH_TIMEOUT_S = 30
_MAX_READ_BYTES = 1_048_576          # 1 MiB per file
_DEFAULT_READ_BYTES = 200_000        # ~200 KiB
_MAX_GREP_BYTES = 5_242_880          # 5 MiB total scanned
_MAX_GREP_RESULTS = 200
_MAX_GLOB_RESULTS = 5_000
_MAX_LS_ENTRIES = 5_000
_MAX_BASH_OUTPUT_BYTES = 102_400     # 100 KiB per stream


def _safe_resolve(
    *,
    workspace_dir: Path,
    user_path: str,
    op: str,
    allow_write: bool = False,
) -> Path | str:
    """Resolve `user_path` (relative) against `workspace_dir`, enforcing:

    - result must live under workspace_dir (no `..` escape, no abs paths)
    - result must not be inside a protected prefix (.git/, node_modules/, etc.)
    - if `allow_write=False` (read/list ops) we still gate against protected prefixes
      so LLM can't probe internals; write/edit add a stricter mode check below.

    Returns the absolute Path on success, or a string error message on failure.
    The caller should branch on `isinstance(result, Path)`.
    """
    if not isinstance(user_path, str) or not user_path:
        return f"{op}: path must be a non-empty string"
    if user_path.startswith("/") or user_path.startswith("~"):
        return f"{op}: absolute paths are not allowed; pass a workspace-relative path"
    if "\0" in user_path:
        return f"{op}: path contains NUL byte"
    # Normalise separators.
    normalised = user_path.replace("\\", "/")
    # Reject obvious escapes; the resolve() + is_relative_to() check below
    # is the actual safety net but we early-fail for clarity in tool output.
    if normalised.startswith("../") or normalised == ".." or "/../" in normalised:
        return f"{op}: '..' is not allowed in path"
    try:
        resolved = (workspace_dir / normalised).resolve()
    except OSError as exc:
        return f"{op}: cannot resolve path ({exc})"
    if not resolved.is_relative_to(workspace_dir):
        return f"{op}: path escapes workspace root"
    if is_protected_prefix(normalised):
        if allow_write:
            return f"{op}: refusing to touch protected prefix ({normalised.split('/')[0]}/)"
        # Read-side: just refuse; prevents LLM from probing .git internals.
        return f"{op}: refusing to read protected prefix ({normalised.split('/')[0]}/)"
    return resolved


def _read_text_capped(path: Path, *, max_bytes: int) -> tuple[str, bool]:
    """Read file as text, capped at max_bytes. Returns (text, truncated)."""
    size = path.stat().st_size
    if size <= max_bytes:
        return path.read_text(errors="replace"), False
    # Truncated read: still text-decode (best effort).
    raw = path.read_bytes()[:max_bytes]
    return raw.decode("utf-8", errors="replace"), True


async def built_in_invoke_bash(
    arguments: dict[str, Any],
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    call_id: UUID,
    actor_id: UUID,
) -> dict[str, Any]:
    """Execute a shell command in the workspace dir (in-process asyncio.subprocess).

    Arguments:
      command: str — required
      cwd: str — optional, default workspace_dir
      timeout_seconds: int — optional, default 30, max 300

    Returns: {stdout, stderr, exit_code, duration_ms, cwd}
    Errors: {error: ...} (not raised — LLM-friendly).
    """
    if workspace_id is None:
        return {"error": "workspace_id required for bash tool"}
    command = (arguments.get("command") or "").strip()
    if not command:
        return {"error": "command is required"}
    try:
        timeout_s = int(arguments.get("timeout_seconds") or _DEFAULT_BASH_TIMEOUT_S)
    except (TypeError, ValueError):
        return {"error": "timeout_seconds must be an integer"}
    timeout_s = max(1, min(_MAX_BASH_TIMEOUT_S, timeout_s))

    _log.info(
        "tool.bash_executed tenant=%s workspace=%s call=%s timeout=%ds",
        tenant_id, workspace_id, call_id, timeout_s,
    )

    # Resolve workspace dir.
    settings = _get_settings()
    ws_dir = resolve_workspace_dir(str(workspace_id), workspace_root=settings.workspace_root)
    try:
        ensure_workspace_dir(ws_dir)
    except OSError as exc:
        return {"error": f"workspace_dir unavailable: {exc}"}

    # cwd must be workspace_dir or a whitelisted subdir (tmp, .cache).
    cwd_arg = (arguments.get("cwd") or "").strip() or "."
    resolved_cwd = _safe_resolve(
        workspace_dir=ws_dir, user_path=cwd_arg, op="bash", allow_write=False
    )
    if isinstance(resolved_cwd, str):
        return {"error": resolved_cwd}
    cwd_path = resolved_cwd

    started = _asyncio.get_event_loop().time()
    try:
        proc = await _asyncio.create_subprocess_shell(
            command,
            stdout=_asyncio.subprocess.PIPE,
            stderr=_asyncio.subprocess.PIPE,
            cwd=str(cwd_path),
        )
        try:
            stdout_bytes, stderr_bytes = await _asyncio.wait_for(
                proc.communicate(), timeout=timeout_s
            )
        except _asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            duration_ms = int((_asyncio.get_event_loop().time() - started) * 1000)
            return {
                "stdout": "",
                "stderr": f"[timeout after {timeout_s}s — process killed]",
                "exit_code": -1,
                "duration_ms": duration_ms,
                "cwd": str(cwd_path),
            }
    except (OSError, ValueError) as exc:
        return {"error": f"failed to spawn shell: {exc}"}

    duration_ms = int((_asyncio.get_event_loop().time() - started) * 1000)

    def _cap(buf: bytes) -> tuple[str, bool]:
        if len(buf) <= _MAX_BASH_OUTPUT_BYTES:
            return buf.decode("utf-8", errors="replace"), False
        return (buf[:_MAX_BASH_OUTPUT_BYTES].decode("utf-8", errors="replace") +
                f"\n…[truncated, {len(buf) - _MAX_BASH_OUTPUT_BYTES} more bytes]"), True

    stdout, stdout_trunc = _cap(stdout_bytes or b"")
    stderr, stderr_trunc = _cap(stderr_bytes or b"")

    await _audit(
        "tool.bash_executed",
        {
            "command": command[:2000],
            "cwd": str(cwd_path),
            "exit_code": proc.returncode,
            "duration_ms": duration_ms,
            "stdout_bytes": len(stdout_bytes or b""),
            "stderr_bytes": len(stderr_bytes or b""),
            "truncated": stdout_trunc or stderr_trunc,
        },
        tenant_id=tenant_id, actor_id=actor_id, call_id=call_id,
        workspace_id=workspace_id,
    )

    return {
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": proc.returncode,
        "duration_ms": duration_ms,
        "cwd": str(cwd_path),
        "truncated": stdout_trunc or stderr_trunc,
    }


async def built_in_invoke_read_file(
    arguments: dict[str, Any],
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    call_id: UUID,
    actor_id: UUID,
) -> dict[str, Any]:
    """Read a text file under the workspace root.

    Arguments:
      path: str — required (relative to workspace_dir)
      max_bytes: int — optional, default 200_000, max 1_048_576
      start_line: int — optional, 0-indexed, default 0
      end_line: int — optional, exclusive, default EOF

    Returns: {path, content, total_lines, encoding, truncated}
    """
    if workspace_id is None:
        return {"error": "workspace_id required for read_file"}
    path_arg = (arguments.get("path") or "").strip()
    if not path_arg:
        return {"error": "path is required"}
    try:
        max_bytes = int(arguments.get("max_bytes") or _DEFAULT_READ_BYTES)
    except (TypeError, ValueError):
        return {"error": "max_bytes must be an integer"}
    max_bytes = max(1_000, min(_MAX_READ_BYTES, max_bytes))
    try:
        start_line = max(0, int(arguments.get("start_line") or 0))
        end_line_input = arguments.get("end_line")
        end_line = int(end_line_input) if end_line_input is not None else None
    except (TypeError, ValueError):
        return {"error": "start_line / end_line must be integers"}

    settings = _get_settings()
    ws_dir = resolve_workspace_dir(str(workspace_id), workspace_root=settings.workspace_root)
    resolved = _safe_resolve(workspace_dir=ws_dir, user_path=path_arg, op="read_file")
    if isinstance(resolved, str):
        return {"error": resolved}
    file_path = resolved

    if not file_path.exists():
        return {"error": f"file not found: {path_arg}"}
    if not file_path.is_file():
        return {"error": f"not a regular file: {path_arg}"}

    try:
        text, truncated = _read_text_capped(file_path, max_bytes=max_bytes)
    except (OSError, UnicodeDecodeError) as exc:
        return {"error": f"read failed: {exc}"}

    lines = text.splitlines()
    total_lines = len(text.splitlines())
    if end_line is not None:
        lines = lines[start_line:end_line]
    else:
        lines = lines[start_line:]
    content = "\n".join(lines)
    if content and not content.endswith("\n"):
        content += "\n"

    await _audit(
        "tool.fs_read",
        {
            "tool": "read_file",
            "path": path_arg,
            "bytes_read": sum(len(l.encode("utf-8")) for l in lines) + (1 if lines else 0),
            "truncated": truncated,
        },
        tenant_id=tenant_id, actor_id=actor_id, call_id=call_id,
        workspace_id=workspace_id,
    )

    return {
        "path": path_arg,
        "content": content,
        "total_lines": total_lines,
        "encoding": "utf-8",
        "truncated": truncated,
    }


async def built_in_invoke_write_file(
    arguments: dict[str, Any],
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    call_id: UUID,
    actor_id: UUID,
) -> dict[str, Any]:
    """Write a text file under the workspace root (in-process)."""
    if workspace_id is None:
        return {"error": "workspace_id required for write_file"}
    path_arg = (arguments.get("path") or "").strip()
    content = arguments.get("content")
    if not path_arg:
        return {"error": "path is required"}
    if not isinstance(content, str):
        return {"error": "content must be a string"}
    create_parents = bool(arguments.get("create_parents"))

    settings = _get_settings()
    ws_dir = resolve_workspace_dir(str(workspace_id), workspace_root=settings.workspace_root)
    resolved = _safe_resolve(
        workspace_dir=ws_dir, user_path=path_arg, op="write_file", allow_write=True
    )
    if isinstance(resolved, str):
        return {"error": resolved}
    file_path = resolved

    _log.info(
        "tool.fs_access op=write tenant=%s workspace=%s call=%s path=%s bytes=%d",
        tenant_id, workspace_id, call_id, path_arg, len(content.encode("utf-8")),
    )

    if create_parents:
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return {"error": f"mkdir failed: {exc}"}
    elif not file_path.parent.exists():
        return {"error": f"parent directory does not exist (pass create_parents=true to auto-create)"}

    try:
        file_path.write_text(content, encoding="utf-8")
    except OSError as exc:
        return {"error": f"write failed: {exc}"}

    await _audit(
        "tool.fs_write",
        {
            "tool": "write_file",
            "path": path_arg,
            "bytes_written": len(content.encode("utf-8")),
            "create_parents": create_parents,
        },
        tenant_id=tenant_id, actor_id=actor_id, call_id=call_id,
        workspace_id=workspace_id,
    )

    return {
        "path": path_arg,
        "bytes_written": len(content.encode("utf-8")),
        "mode": "w",
    }


async def built_in_invoke_edit_file(
    arguments: dict[str, Any],
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    call_id: UUID,
    actor_id: UUID,
) -> dict[str, Any]:
    """Replace `old_text` with `new_text` in a file (exactly once)."""
    if workspace_id is None:
        return {"error": "workspace_id required for edit_file"}
    path_arg = (arguments.get("path") or "").strip()
    old_text = arguments.get("old_text")
    new_text = arguments.get("new_text")
    if not path_arg:
        return {"error": "path is required"}
    if not isinstance(old_text, str) or not old_text:
        return {"error": "old_text is required and must be a non-empty string"}
    if not isinstance(new_text, str):
        return {"error": "new_text must be a string"}

    settings = _get_settings()
    ws_dir = resolve_workspace_dir(str(workspace_id), workspace_root=settings.workspace_root)
    resolved = _safe_resolve(
        workspace_dir=ws_dir, user_path=path_arg, op="edit_file", allow_write=True
    )
    if isinstance(resolved, str):
        return {"error": resolved}
    file_path = resolved

    if not file_path.exists() or not file_path.is_file():
        return {"error": f"file not found: {path_arg}"}

    try:
        original = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {"error": f"read failed: {exc}"}

    occurrences = original.count(old_text)
    if occurrences == 0:
        return {"error": "old_text not found in file; no edits applied"}
    if occurrences > 1:
        return {
            "error": (
                f"old_text matched {occurrences} times; need exactly 1. "
                "Make old_text more specific."
            )
        }

    edited = original.replace(old_text, new_text, 1)
    try:
        file_path.write_text(edited, encoding="utf-8")
    except OSError as exc:
        return {"error": f"write failed: {exc}"}

    _log.info(
        "tool.fs_access op=edit tenant=%s workspace=%s call=%s path=%s replacements=1",
        tenant_id, workspace_id, call_id, path_arg,
    )

    await _audit(
        "tool.fs_edit",
        {"tool": "edit_file", "path": path_arg, "replacements": 1},
        tenant_id=tenant_id, actor_id=actor_id, call_id=call_id,
        workspace_id=workspace_id,
    )

    return {
        "path": path_arg,
        "replacements": 1,
        "preview": new_text[:400],
    }


async def built_in_invoke_ls(
    arguments: dict[str, Any],
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    call_id: UUID,
    actor_id: UUID,
) -> dict[str, Any]:
    """List a directory under the workspace root."""
    if workspace_id is None:
        return {"error": "workspace_id required for ls"}
    path_arg = (arguments.get("path") or "").strip() or "."
    recursive = bool(arguments.get("recursive"))
    try:
        max_depth = int(arguments.get("max_depth") or 3)
    except (TypeError, ValueError):
        return {"error": "max_depth must be an integer"}
    max_depth = max(0, min(10, max_depth))
    include_hidden = bool(arguments.get("include_hidden"))

    settings = _get_settings()
    ws_dir = resolve_workspace_dir(str(workspace_id), workspace_root=settings.workspace_root)
    try:
        ensure_workspace_dir(ws_dir)
    except OSError as exc:
        return {"error": f"workspace_dir unavailable: {exc}"}
    resolved = _safe_resolve(workspace_dir=ws_dir, user_path=path_arg, op="ls")
    if isinstance(resolved, str):
        return {"error": resolved}
    dir_path = resolved

    if not dir_path.exists():
        return {"error": f"directory not found: {path_arg}"}
    if not dir_path.is_dir():
        return {"error": f"not a directory: {path_arg}"}

    entries: list[dict[str, Any]] = []

    def _walk(directory: Path, depth: int) -> None:
        if len(entries) >= _MAX_LS_ENTRIES:
            return
        try:
            for child in sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                if len(entries) >= _MAX_LS_ENTRIES:
                    return
                rel = str(child.relative_to(ws_dir))
                if is_protected_prefix(rel):
                    continue
                if not include_hidden and child.name.startswith("."):
                    continue
                try:
                    stat = child.stat()
                    entry = {
                        "name": child.name,
                        "path": rel,
                        "type": "dir" if child.is_dir() else "file",
                        "size": stat.st_size if child.is_file() else None,
                        "mtime": int(stat.st_mtime),
                    }
                except OSError:
                    entry = {"name": child.name, "path": rel, "type": "?"}
                entries.append(entry)
                if recursive and child.is_dir() and depth < max_depth:
                    _walk(child, depth + 1)
        except PermissionError:
            return

    _walk(dir_path, 0)
    await _audit(
        "tool.fs_list",
        {"tool": "ls", "path": path_arg, "count": len(entries), "truncated": len(entries) >= _MAX_LS_ENTRIES},
        tenant_id=tenant_id, actor_id=actor_id, call_id=call_id,
        workspace_id=workspace_id,
    )
    return {
        "path": path_arg,
        "entries": entries,
        "total": len(entries),
        "truncated": len(entries) >= _MAX_LS_ENTRIES,
    }


async def built_in_invoke_glob(
    arguments: dict[str, Any],
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    call_id: UUID,
    actor_id: UUID,
) -> dict[str, Any]:
    """Glob files under the workspace root (gitignore-style)."""
    if workspace_id is None:
        return {"error": "workspace_id required for glob"}
    pattern = (arguments.get("pattern") or "").strip()
    if not pattern:
        return {"error": "pattern is required"}
    cwd_arg = (arguments.get("cwd") or "").strip() or "."
    try:
        max_results = int(arguments.get("max_results") or 1_000)
    except (TypeError, ValueError):
        return {"error": "max_results must be an integer"}
    max_results = max(1, min(_MAX_GLOB_RESULTS, max_results))

    settings = _get_settings()
    ws_dir = resolve_workspace_dir(str(workspace_id), workspace_root=settings.workspace_root)
    try:
        ensure_workspace_dir(ws_dir)
    except OSError as exc:
        return {"error": f"workspace_dir unavailable: {exc}"}
    resolved_cwd = _safe_resolve(workspace_dir=ws_dir, user_path=cwd_arg, op="glob")
    if isinstance(resolved_cwd, str):
        return {"error": resolved_cwd}
    cwd_path = resolved_cwd

    # Run glob. fnmatch is more permissive than pathlib glob — use fnmatch
    # on a recursive walk to honour ** properly.
    matches: list[str] = []
    truncated = False
    pattern_norm = pattern.replace("\\", "/")
    if pattern_norm.startswith("/"):
        return {"error": "pattern must not start with /"}
    if ".." in pattern_norm.split("/"):
        return {"error": "pattern must not contain '..'"}

    def _matches(rel: str) -> bool:
        # fnmatch doesn't support ** natively but pathlib glob does. We
        # delegate to Path.glob for `**` patterns and fall back to fnmatch
        # for simple patterns. Simplest: use fnmatchcase on basename + full
        # relative path for ** matching by segment count.
        if "**" not in pattern_norm:
            return _fnmatch.fnmatchcase(rel, pattern_norm) or _fnmatch.fnmatchcase(
                rel.split("/")[-1], pattern_norm.split("/")[-1]
            )
        # ** handling: split pattern into segments; rel must have the
        # same segments with ** acting as zero-or-more dirs.
        pat_parts = pattern_norm.split("/")
        rel_parts = rel.split("/")
        pi = ri = 0
        while pi < len(pat_parts):
            seg = pat_parts[pi]
            if seg == "**":
                if pi == len(pat_parts) - 1:
                    return True  # trailing ** matches anything below
                # try to match the rest against any suffix of rel_parts
                for j in range(ri, len(rel_parts) - (len(pat_parts) - pi - 1) + 1):
                    if _matches("/".join(rel_parts[j:])):
                        return True
                return False
            if ri >= len(rel_parts):
                return False
            if not _fnmatch.fnmatchcase(rel_parts[ri], seg):
                return False
            pi += 1
            ri += 1
        return ri == len(rel_parts)

    try:
        for child in cwd_path.rglob("*"):
            if len(matches) >= max_results:
                truncated = True
                break
            try:
                rel = str(child.relative_to(ws_dir))
            except ValueError:
                continue
            if is_protected_prefix(rel):
                continue
            if _matches(rel):
                matches.append(rel)
    except OSError as exc:
        return {"error": f"glob failed: {exc}"}

    await _audit(
        "tool.fs_list",
        {"tool": "glob", "pattern": pattern, "count": len(matches), "truncated": truncated},
        tenant_id=tenant_id, actor_id=actor_id, call_id=call_id,
        workspace_id=workspace_id,
    )

    return {
        "pattern": pattern,
        "matches": sorted(matches),
        "count": len(matches),
        "truncated": truncated,
    }


async def built_in_invoke_grep(
    arguments: dict[str, Any],
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
    call_id: UUID,
    actor_id: UUID,
) -> dict[str, Any]:
    """Search file contents under the workspace root for a regex pattern."""
    if workspace_id is None:
        return {"error": "workspace_id required for grep"}
    pattern = arguments.get("pattern")
    if not isinstance(pattern, str) or not pattern:
        return {"error": "pattern is required and must be a non-empty string"}
    cwd_arg = (arguments.get("cwd") or "").strip() or "."
    include = (arguments.get("include") or "").strip() or "*"
    try:
        max_results = int(arguments.get("max_results") or _MAX_GREP_RESULTS)
    except (TypeError, ValueError):
        return {"error": "max_results must be an integer"}
    max_results = max(1, min(_MAX_GREP_RESULTS * 2, max_results))
    case_insensitive = bool(arguments.get("case_insensitive"))

    try:
        flags = _re_fs.IGNORECASE if case_insensitive else 0
        regex = _re_fs.compile(pattern, flags=flags)
    except _re_fs.error as exc:
        return {"error": f"invalid regex: {exc}"}

    settings = _get_settings()
    ws_dir = resolve_workspace_dir(str(workspace_id), workspace_root=settings.workspace_root)
    try:
        ensure_workspace_dir(ws_dir)
    except OSError as exc:
        return {"error": f"workspace_dir unavailable: {exc}"}
    resolved_cwd = _safe_resolve(workspace_dir=ws_dir, user_path=cwd_arg, op="grep")
    if isinstance(resolved_cwd, str):
        return {"error": resolved_cwd}
    cwd_path = resolved_cwd

    if not cwd_path.exists() or not cwd_path.is_dir():
        return {"error": f"cwd not a directory: {cwd_arg}"}

    matches: list[dict[str, Any]] = []
    total_bytes_scanned = 0
    truncated = False

    try:
        candidates = sorted(cwd_path.rglob("*")) if include in ("*", "**/*") else sorted(cwd_path.rglob(include))
    except OSError as exc:
        return {"error": f"rglob failed: {exc}"}

    for path in candidates:
        if not path.is_file():
            continue
        try:
            rel = str(path.relative_to(ws_dir))
        except ValueError:
            continue
        if is_protected_prefix(rel):
            continue
        try:
            size = path.stat().st_size
            if total_bytes_scanned + size > _MAX_GREP_BYTES:
                truncated = True
                break
            text = path.read_text(errors="replace")
            total_bytes_scanned += len(text.encode("utf-8", errors="replace"))
        except (OSError, UnicodeDecodeError):
            continue
        for line_num, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                if len(matches) >= max_results:
                    truncated = True
                    break
                matches.append({
                    "path": rel,
                    "line_number": line_num,
                    "line": line.strip()[:500],
                })
        if truncated:
            break

    await _audit(
        "tool.fs_search",
        {"tool": "grep", "pattern": pattern, "cwd": cwd_arg, "count": len(matches), "truncated": truncated},
        tenant_id=tenant_id, actor_id=actor_id, call_id=call_id,
        workspace_id=workspace_id,
    )
    return {
        "pattern": pattern,
        "matches": matches,
        "count": len(matches),
        "truncated": truncated,
    }


# Settings accessor — custom tools read workspace_root at call time so
# tests can monkey-patch the registry's _workspace_root or pass it through
# to the registry constructor in lifespan.

_settings_singleton: dict[str, Any] | None = None
_audit_recorder_singleton: ToolAuditRecorder | None = None


def bind_settings_for_tools(settings: Any) -> None:
    """Lifespan calls this once at boot so tools can read settings.workspace_root."""
    global _settings_singleton
    _settings_singleton = settings


def bind_audit_recorder(recorder: ToolAuditRecorder) -> None:
    """Lifespan calls this once so built-in tools can write audit_log rows.

    Test code may set ``_audit_recorder_singleton`` to a stub directly.
    """
    global _audit_recorder_singleton
    _audit_recorder_singleton = recorder


def _get_settings() -> Any:
    if _settings_singleton is None:
        raise RuntimeError(
            "settings not bound; lifespan must call bind_settings_for_tools() at startup"
        )
    return _settings_singleton


async def _audit(event_type: str, payload: dict[str, Any], **ctx: Any) -> None:
    """Best-effort audit_log write. No-op if recorder not bound."""
    rec = _audit_recorder_singleton
    if rec is None:
        return
    try:
        await rec.record(
            event_type=event_type,
            payload=payload,
            tenant_id=ctx["tenant_id"],
            actor_id=ctx["actor_id"],
            call_id=ctx["call_id"],
            workspace_id=ctx.get("workspace_id"),
        )
    except Exception:
        # recorder.record already swallows DB errors, but defensive
        pass