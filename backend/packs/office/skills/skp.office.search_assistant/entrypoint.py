"""Entry-point for ``skp.office.search_assistant``.

Reranks a candidate list against a query. When the sandbox provides
``QZDAP_LLM_HTTP_URL`` + ``QZDAP_LLM_API_KEY`` + ``QZDAP_LLM_MODEL`` the
entry-point asks the LLM to score each candidate (returned as
``results: [{rank, score, snippet}]``); without those env vars it
falls back to a deterministic reciprocal-rank placeholder tagged
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
            "temperature": 0.0,
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


def _placeholder(query: str, top_k: int) -> dict:
    return {
        "results": [
            {
                "rank": i + 1,
                "score": 1.0 / (i + 1),
                "snippet": f"hit {i + 1} for {query!r}",
            }
            for i in range(top_k)
        ],
        "confidence": "low",
    }


def main(argv: list[str]) -> dict:
    raw = argv[-1] if len(argv) > 1 else ""
    try:
        args = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        args = {}
    query = args.get("query", "")
    top_k = int(args.get("top_k", 5))
    candidates = args.get("candidates") or []
    env = _llm_env()
    if env is None or not candidates:
        return _placeholder(query, top_k)
    cand_lines = [
        f"[{i}] {c.get('title', '')} — {c.get('snippet', '')[:200]}"
        for i, c in enumerate(candidates[:50])
    ]
    prompt = (
        f"Rerank these candidates against the query {query!r}. Reply "
        "with JSON: {results: [{rank: 1-based int, score: 0..1, "
        "snippet: <= 200 chars}]}. Pick top " + str(top_k) + ".\n\n"
        + "\n".join(cand_lines)
    )
    parsed = _call_llm_json(prompt=prompt, env=env)
    results = parsed.get("results") if isinstance(parsed, dict) else None
    if not results or not isinstance(results, list):
        return _placeholder(query, top_k)
    cleaned = [
        {
            "rank": i + 1,
            "score": float(r.get("score", 0.0)),
            "snippet": str(r.get("snippet", ""))[:200],
        }
        for i, r in enumerate(results[:top_k])
    ]
    return {"results": cleaned, "confidence": "high"}


if __name__ == "__main__":
    print(json.dumps(main(sys.argv)))
