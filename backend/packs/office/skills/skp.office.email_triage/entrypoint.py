"""Entry-point for ``skp.office.email_triage``.

Classifies an incoming email. When the sandbox provides
``QZDAP_LLM_HTTP_URL`` + ``QZDAP_LLM_API_KEY`` + ``QZDAP_LLM_MODEL`` the
entry-point asks the LLM for ``{priority, category, suggested_reply}``
JSON; without those env vars it falls back to a deterministic
placeholder tagged ``confidence: "low"``.
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
            "temperature": 0.1,
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
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
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
    body = args.get("email_body", "")
    env = _llm_env()
    if env is None:
        return {
            "priority": "P2",
            "category": "uncategorized",
            "suggested_reply": f"acknowledged ({len(body)} chars)",
            "confidence": "low",
        }
    prompt = (
        "Triage the email below. Reply with JSON: {priority: one of "
        "[P0, P1, P2, P3], category: short noun phrase, suggested_reply: "
        "<= 200 chars polite acknowledgement}. Do not invent facts.\n\n"
        + body[:4000]
    )
    parsed = _call_llm_json(prompt=prompt, env=env)
    if not parsed or "priority" not in parsed:
        return {
            "priority": "P2",
            "category": "uncategorized",
            "suggested_reply": f"acknowledged ({len(body)} chars)",
            "confidence": "low",
        }
    return {
        "priority": str(parsed.get("priority", "P2")),
        "category": str(parsed.get("category", "uncategorized")),
        "suggested_reply": str(parsed.get("suggested_reply", ""))[:400],
        "confidence": "high",
    }


if __name__ == "__main__":
    print(json.dumps(main(sys.argv)))
