"""Entry-point for ``skp.office.search_assistant``.

Reranks a candidate list against a query.

历史: 之前会从 ``QZDAP_LLM_HTTP_URL`` + ``QZDAP_LLM_API_KEY`` + ``QZDAP_LLM_MODEL``
读 env 调 LLM 重排序. env 路径已下线 (LLM 凭据统一管理侧配).

现在永远走确定性 reciprocal-rank 占位符 + ``confidence: "low"`` fallback,
直到 P7+ 让 sandbox runtime 把管理侧解密后的凭据 push 到子进程 env.
"""

from __future__ import annotations

import json
import sys


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
    return _placeholder(query, top_k)


if __name__ == "__main__":
    print(json.dumps(main(sys.argv)))
