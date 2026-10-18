"""Entry-point for ``skp.office.email_triage``.

Classifies an incoming email.

历史: 之前会从 ``QZDAP_LLM_HTTP_URL`` + ``QZDAP_LLM_API_KEY`` + ``QZDAP_LLM_MODEL``
读 env 调 LLM 做分类. env 路径已下线 (LLM 凭据统一管理侧配).

现在永远走确定性占位符 + ``confidence: "low"`` fallback, 直到 P7+ 让
sandbox runtime 把管理侧解密后的凭据 push 到子进程 env.
"""

from __future__ import annotations

import json
import sys


def main(argv: list[str]) -> dict:
    raw = argv[-1] if len(argv) > 1 else ""
    try:
        args = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        args = {}
    body = args.get("email_body", "")
    return {
        "priority": "P2",
        "category": "uncategorized",
        "suggested_reply": f"acknowledged ({len(body)} chars)",
        "confidence": "low",
    }


if __name__ == "__main__":
    print(json.dumps(main(sys.argv)))
