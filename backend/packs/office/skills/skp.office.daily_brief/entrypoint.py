"""Entry-point for ``skp.office.daily_brief``.

Aggregates a markdown summary from a list of events. When the sandbox
provides ``QZDAP_LLM_HTTP_URL`` + ``QZDAP_LLM_API_KEY`` + ``QZDAP_LLM_MODEL``
the entry-point calls the configured LLM for a richer narrative; if
either is missing it falls back to a deterministic placeholder and
tags the result with ``confidence: "low"`` so downstream tools can
flag low-trust output.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def _llm_env() -> tuple[str, str, str] | None:
    base = os.environ.get("QZDAP_LLM_HTTP_URL", "").rstrip("/")
    key = os.environ.get("QZDAP_LLM_API_KEY", "")
    model = os.environ.get("QZDAP_LLM_MODEL", "")
    if not base or not key or not model:
        return None
    return base, key, model


def _call_llm(*, prompt: str, env: tuple[str, str, str]) -> str | None:
    base, key, model = env
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        }
    ).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310
        f"{base}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    try:
        return str(payload["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError):
        return None


def _placeholder(events: list) -> dict:
    return {
        "markdown": f"# Daily Brief\n\n- {len(events)} events summarised\n",
        "headline": "all quiet",
        "confidence": "low",
    }


def main(argv: list[str]) -> dict:
    raw = argv[-1] if len(argv) > 1 else ""
    try:
        args = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        args = {}
    events = args.get("events") or []
    env = _llm_env()
    if env is None:
        return _placeholder(events)
    summary_lines = [
        f"- [{e.get('severity', 'info')}] {e.get('title', '')}".strip()
        for e in events[:20]
    ]
    prompt = (
        "Summarise the following ops events into a 3-bullet daily "
        "brief markdown body (do not invent facts; keep under 400 chars):\n"
        + "\n".join(summary_lines)
    )
    md = _call_llm(prompt=prompt, env=env)
    if not md:
        return _placeholder(events)
    return {
        "markdown": md,
        "headline": "llm-generated",
        "confidence": "high",
    }


if __name__ == "__main__":
    print(json.dumps(main(sys.argv)))
