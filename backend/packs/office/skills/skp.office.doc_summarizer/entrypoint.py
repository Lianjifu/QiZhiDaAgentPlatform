"""Entry-point for ``skp.office.doc_summarizer``.

Generates a TLDR + action items list from a document. When the sandbox
provides ``QZDAP_LLM_HTTP_URL`` + ``QZDAP_LLM_API_KEY`` + ``QZDAP_LLM_MODEL``
the entry-point asks the LLM to draft the summary (returned as JSON
``{"tldr": ..., "action_items": [...]}``); without those env vars it
falls back to a deterministic placeholder and tags the result with
``confidence: "low"``.
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


def _call_llm_json(*, prompt: str, env: tuple[str, str, str]) -> dict | None:
    base, key, model = env
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
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
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    try:
        content = payload["choices"][0]["message"]["content"]
        parsed = json.loads(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def main(argv: list[str]) -> dict:
    raw = argv[-1] if len(argv) > 1 else ""
    try:
        args = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        args = {}
    text = args.get("document_text", "")
    max_chars = int(args.get("max_tldr_chars", 280))
    env = _llm_env()
    if env is None:
        body = text[:max_chars]
        return {
            "tldr": body + ("…" if len(text) > max_chars else ""),
            "action_items": [],
            "confidence": "low",
        }
    prompt = (
        "Summarise the document below into a JSON object with keys "
        f"`tldr` (<= {max_chars} chars) and `action_items` (array of "
        "strings). Do not invent facts.\n\n" + text[:8000]
    )
    parsed = _call_llm_json(prompt=prompt, env=env)
    if not parsed or "tldr" not in parsed:
        body = text[:max_chars]
        return {
            "tldr": body + ("…" if len(text) > max_chars else ""),
            "action_items": [],
            "confidence": "low",
        }
    return {
        "tldr": str(parsed["tldr"])[:max_chars],
        "action_items": list(parsed.get("action_items") or []),
        "confidence": "high",
    }


if __name__ == "__main__":
    print(json.dumps(main(sys.argv)))
