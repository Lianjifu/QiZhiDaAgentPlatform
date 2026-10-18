"""Entry-point for ``skp.office.doc_summarizer``.

Generates a TLDR + action items list from a document.

历史: 之前会从 ``QZDAP_LLM_HTTP_URL`` + ``QZDAP_LLM_API_KEY`` + ``QZDAP_LLM_MODEL``
读 env 调 LLM 拿更准的摘要. 这条 env 路径已下线 (LLM 凭据统一在
管理侧 → 模型管理 配, 由 ModelService 解密; sandbox 子进程拿不到).

现在永远走确定性占位符 + ``confidence: "low"`` fallback, 直到后续工单
让 sandbox runtime 把管理侧解密后的凭据 push 到子进程 env (P7+).
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
    text = args.get("document_text", "")
    max_chars = int(args.get("max_tldr_chars", 280))
    body = text[:max_chars]
    return {
        "tldr": body + ("…" if len(text) > max_chars else ""),
        "action_items": [],
        "confidence": "low",
    }


if __name__ == "__main__":
    print(json.dumps(main(sys.argv)))
