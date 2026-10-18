"""Entry-point for ``skp.office.daily_brief``.

Aggregates a markdown summary from a list of events.

历史: 之前会从 ``QZDAP_LLM_HTTP_URL`` + ``QZDAP_LLM_API_KEY`` + ``QZDAP_LLM_MODEL``
读 env 调 LLM 拿更丰富的 narrative. env 路径已下线 (LLM 凭据统一管理侧配).

现在永远走确定性占位符 + ``confidence: "low"`` fallback, 直到 P7+ 让
sandbox runtime 把管理侧解密后的凭据 push 到子进程 env.
"""

from __future__ import annotations

import json
import sys


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
    return _placeholder(events)


if __name__ == "__main__":
    print(json.dumps(main(sys.argv)))
