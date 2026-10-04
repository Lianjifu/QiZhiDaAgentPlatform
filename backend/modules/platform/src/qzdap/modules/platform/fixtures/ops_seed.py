"""Frontend-aligned admin console seed (额度 / 渠道 / 评测 / 回归 / 反馈 / 链路 / 审计 / 指标)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_SEED_PATH = Path(__file__).with_name("ops_seed.json")
SEED: dict[str, list[dict[str, Any]]] = json.loads(_SEED_PATH.read_text(encoding="utf-8"))
