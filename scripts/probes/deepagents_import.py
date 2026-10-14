"""Probe whether a usable `deepagents`-style package exists on PyPI.

Per §2.5 阻塞 4 of docs/refactor/session-module-refactor-plan.md:
- Try the three candidate package names: deepagents, langchain_deepagents, deep_agents.
- Record presence, version, and minimum-usable API surface (create_deep_agent, DeepAgent, SubAgent).
- Run with `uv run --with <name> --with <name> ...` so each candidate gets a clean venv.

Usage:
    uv run --with deepagents --with langchain_deepagents \
        python scripts/probes/deepagents_import.py

Exit code is non-zero ONLY if every candidate is missing AND no usable API
was found. Successful probes exit 0 and print a JSON-ish summary so the
result document can be machine-generated later.
"""

from __future__ import annotations

import importlib
import json
import sys
from dataclasses import asdict, dataclass, field
from typing import Any


CANDIDATE_PACKAGES: tuple[str, ...] = (
    "deepagents",
    "langchain_deepagents",
    "deep_agents",
)

CANDIDATE_API_ATTRS: tuple[str, ...] = (
    "create_deep_agent",
    "DeepAgent",
    "SubAgent",
    "PlanAndExecute",
    "CompiledDeepAgent",
)


@dataclass(slots=True)
class ProbeResult:
    """Per-candidate probe outcome."""

    package: str
    installed: bool
    version: str | None = None
    api_attrs: list[str] = field(default_factory=list)
    import_error: str | None = None


def _probe_package(name: str) -> ProbeResult:
    """Try to import a package and report what is visible."""
    try:
        module = importlib.import_module(name)
    except ImportError as exc:
        return ProbeResult(
            package=name,
            installed=False,
            import_error=str(exc),
        )

    api_found = [attr for attr in CANDIDATE_API_ATTRS if hasattr(module, attr)]
    return ProbeResult(
        package=name,
        installed=True,
        version=getattr(module, "__version__", None),
        api_attrs=api_found,
    )


def main() -> int:
    """Run all probes and emit a JSON summary on stdout."""
    results: list[ProbeResult] = [_probe_package(name) for name in CANDIDATE_PACKAGES]

    payload: dict[str, Any] = {
        "python": sys.version.split()[0],
        "results": [asdict(r) for r in results],
    }

    print(json.dumps(payload, indent=2, ensure_ascii=False))

    any_installed = any(r.installed and r.api_attrs for r in results)
    return 0 if any_installed else 1


if __name__ == "__main__":
    raise SystemExit(main())