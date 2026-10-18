"""Map a workspace_id (UUID) to a host filesystem directory.

Used by agent built-in tools (bash / read_file / write_file / edit_file /
ls / glob / grep) so they can find the workspace the user is working in.

Phase 1 (this module): workspace_dir = settings.workspace_root / str(workspace_id)
Phase 2 (TODO): read admin_workspaces.sandbox_path and use that instead.

Safety contract:
- All paths returned from `resolve_workspace_dir` are absolute and **must**
  be treated as the root of trust by callers. Built-in tools then run every
  user-supplied path through `_safe_resolve()` which checks
  `is_relative_to(workspace_dir)` before any FS access.
- The resolver does NOT create directories; callers do that via `ensure_workspace_dir`
  (lazily, on first tool call).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

_log = logging.getLogger(__name__)


def resolve_workspace_dir(workspace_id: str, *, workspace_root: str) -> Path:
    """Map a workspace_id to its host filesystem directory.

    Pure function: same inputs always return the same absolute Path. Does
    NOT touch the filesystem (no mkdir). Use `ensure_workspace_dir` if
    you need the directory to exist.

    Args:
      workspace_id: workspace UUID (string form, e.g. "325b35e6-...")
      workspace_root: settings.workspace_root (absolute path)

    Returns:
      Absolute Path. Never raises for normal inputs; raises ValueError if
      workspace_id contains path separators (defence against injection).
    """
    if not workspace_id or not isinstance(workspace_id, str):
        raise ValueError("workspace_id must be a non-empty string")
    if "/" in workspace_id or "\\" in workspace_id or "\0" in workspace_id:
        raise ValueError("workspace_id contains path separators")
    if workspace_id in {".", ".."}:
        raise ValueError("workspace_id is a path traversal token")
    root = Path(workspace_root).expanduser().resolve()
    return (root / workspace_id).resolve()


def ensure_workspace_dir(path: Path) -> Path:
    """Create the workspace directory (mode 0o755) if missing. Returns path.

    On permission errors (e.g. workspace_root points at a path we can't
    create) we LOG and re-raise. Tool wrappers translate PermissionError
    into a friendly `{"error": "..."}` payload so the LLM gets a clear
    message instead of an opaque 500.
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _log.warning("ensure_workspace_dir failed path=%s err=%s", path, exc)
        raise
    return path


def is_protected_prefix(rel_path: str) -> bool:
    """Return True if `rel_path` points at a directory we never want LLM tools to touch.

    Protected prefixes are matched against the first path segment of the
    RELATIVE path (after workspace_dir). Hidden dirs (e.g. .git) and
    common generated dirs (node_modules, dist, build, .venv, __pycache__)
    are off-limits for write/edit; read/ls/grep also skip them.
    """
    parts = rel_path.replace("\\", "/").split("/")
    head = parts[0]
    if not head:
        return False
    protected = {
        ".git",
        ".claude",
        ".venv",
        "node_modules",
        "dist",
        "build",
        "__pycache__",
        ".pytest_cache",
        ".next",
        ".turbo",
        "target",  # rust
    }
    return head in protected


__all__ = [
    "ensure_workspace_dir",
    "is_protected_prefix",
    "resolve_workspace_dir",
]


# ── Env override (dev convenience) ──────────────────────────────────
#
# Set QZDAP_WORKSPACE_ROOT=/tmp/qzdap-workspaces in dev to avoid sudo at first
# tool invocation. Lifespan reads this once at boot; per-test code can
# monkey-patch `settings.workspace_root` directly.
_DEFAULT_ENV = "QZDAP_WORKSPACE_ROOT"


def env_workspace_root(default: str | None = None) -> str:
    """Read QZDAP_WORKSPACE_ROOT from env, with fallback to `default`."""
    return os.environ.get(_DEFAULT_ENV) or default or "/var/qzdap/workspaces"