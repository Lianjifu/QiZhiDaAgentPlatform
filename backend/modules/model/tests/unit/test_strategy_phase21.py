"""Phase 21: round-robin + weighted 策略路由 unit tests.

直接调 ModelService._apply_round_robin / _apply_weighted, 验证:
  - round-robin: 多次调用, 起点轮转
  - weighted: dict-list 解析正确, string-list fallback uniform
  - weighted 选了 chosen 排第一, 其他按 weight 降序
"""
from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from qzdap_schema.ids import ModelId

from qzdap.modules.model.application.services import ModelService
from qzdap.modules.model.domain.entities import HealthEvent, Model, RouteRule

TENANT = uuid4()
WORKSPACE = uuid4()


class _MemModels:
    def __init__(self) -> None:
        self.rows: dict[UUID, Model] = {}

    async def add(self, model: Model) -> None:
        self.rows[model.id] = model

    async def get(self, model_id: UUID) -> Model | None:
        return self.rows.get(model_id)

    async def list_for_workspace(self, workspace_id: UUID) -> list[Model]:
        return [m for m in self.rows.values() if m.workspace_id == workspace_id]

    async def update(self, model: Model) -> None:
        self.rows[model.id] = model

    async def delete(self, model_id: UUID) -> None:
        self.rows.pop(model_id, None)


class _MemRoutes:
    def __init__(self) -> None:
        self.rows: dict[UUID, RouteRule] = {}

    async def add(self, route: RouteRule) -> None:
        self.rows[route.id] = route

    async def get(self, route_id: UUID) -> RouteRule | None:
        return self.rows.get(route_id)

    async def list_for_workspace(self, workspace_id: UUID) -> list[RouteRule]:
        return [r for r in self.rows.values() if r.workspace_id == workspace_id]

    async def update(self, route: RouteRule) -> None:
        self.rows[route.id] = route

    async def delete(self, route_id: UUID) -> None:
        self.rows.pop(route_id, None)


def _make_svc() -> ModelService:
    """构造一个轻量 ModelService, 只用 _apply_* 纯函数, 不需要真实 client."""
    # 创建一个 ModelService, 但 _quota_session=None (in-memory fake 没 _s)
    return ModelService(
        models=_MemModels(),  # type: ignore[arg-type]
        providers=_MemProvidersStub(),  # type: ignore[arg-type]
        routes=_MemRoutes(),  # type: ignore[arg-type]
        health=_MemHealthStub(),  # type: ignore[arg-type]
    )


class _MemProvidersStub:
    async def get(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    async def list_for_workspace(self, *_args: Any, **_kwargs: Any) -> list:
        return []

    async def add(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    async def update(self, *_args: Any, **_kwargs: Any) -> None:
        return None


class _MemHealthStub:
    async def add(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    async def list_for_workspace(
        self, *_args: Any, **_kwargs: Any
    ) -> list[HealthEvent]:
        return []


def test_round_robin_rotates_fallback_across_calls() -> None:
    """多次调用 round-robin, 起点轮转, primary 始终第一."""
    svc = _make_svc()
    primary = uuid4()
    f1, f2, f3 = uuid4(), uuid4(), uuid4()
    chain = [ModelId(primary), ModelId(f1), ModelId(f2), ModelId(f3)]
    route_id = uuid4()
    seen_starts: list[UUID] = []
    for _ in range(6):
        result = svc._apply_round_robin(
            workspace_id=WORKSPACE,
            route_id=route_id,
            chain=chain,
            primary_id=primary,
        )
        # primary 始终第一
        assert UUID(str(result[0])) == primary
        # fallback 段 6 次轮转 3 个候选 → 每个被启始 2 次
        seen_starts.append(UUID(str(result[1])))
    # 6 次应覆盖每个 fallback 候选 2 次
    from collections import Counter

    counts = Counter(seen_starts)
    assert counts[f1] == 2
    assert counts[f2] == 2
    assert counts[f3] == 2


def test_round_robin_per_route_independent() -> None:
    """不同 route 的 counter 互不干扰."""
    svc = _make_svc()
    primary = uuid4()
    f1, f2 = uuid4(), uuid4()
    chain = [ModelId(primary), ModelId(f1), ModelId(f2)]
    r1, r2 = uuid4(), uuid4()
    a1 = svc._apply_round_robin(
        workspace_id=WORKSPACE, route_id=r1, chain=chain, primary_id=primary
    )
    a2 = svc._apply_round_robin(
        workspace_id=WORKSPACE, route_id=r2, chain=chain, primary_id=primary
    )
    # r1 走到 f1 (counter 0 → 0, fallback[0]=f1)
    # r2 走到 f1 (counter 0 → 0, fallback[0]=f1)
    assert UUID(str(a1[1])) == f1
    assert UUID(str(a2[1])) == f1
    # 再调一次, r1 走到 f2, r2 走到 f2
    a1b = svc._apply_round_robin(
        workspace_id=WORKSPACE, route_id=r1, chain=chain, primary_id=primary
    )
    a2b = svc._apply_round_robin(
        workspace_id=WORKSPACE, route_id=r2, chain=chain, primary_id=primary
    )
    assert UUID(str(a1b[1])) == f2
    assert UUID(str(a2b[1])) == f2


def test_round_robin_only_primary_no_rotation() -> None:
    """只有 primary 没 fallback → 不 panic, 原样返回."""
    svc = _make_svc()
    primary = uuid4()
    chain = [ModelId(primary)]
    result = svc._apply_round_robin(
        workspace_id=WORKSPACE,
        route_id=uuid4(),
        chain=chain,
        primary_id=primary,
    )
    assert [UUID(str(m)) for m in result] == [primary]


def test_weighted_dict_list_picks_by_weight() -> None:
    """[{id, weight}] 格式 → 按 weight 比例采样首, 其他按 weight 降序."""
    svc = _make_svc()
    primary = uuid4()
    a, b, c = uuid4(), uuid4(), uuid4()
    chain = [ModelId(primary), ModelId(a), ModelId(b), ModelId(c)]
    fb_ids = [
        {"id": str(a), "weight": 1.0},
        {"id": str(b), "weight": 2.0},
        {"id": str(c), "weight": 0.5},
    ]
    seen_first: list[UUID] = []
    for _ in range(50):
        result = svc._apply_weighted(
            chain=chain, primary_id=primary, fallback_model_ids=fb_ids
        )
        assert UUID(str(result[0])) == primary
        seen_first.append(UUID(str(result[1])))
    # 50 次采样, b (weight=2) 出现最多, c (weight=0.5) 最少
    from collections import Counter

    counts = Counter(seen_first)
    assert counts[b] > counts[a]
    assert counts[a] > counts[c]
    # 至少有一个候选被采到过
    assert counts[b] > 0
    assert counts[a] > 0


def test_weighted_string_list_uniform_weight() -> None:
    """string-list (旧格式) → uniform weight, 每条都可能被选."""
    svc = _make_svc()
    primary = uuid4()
    a, b = uuid4(), uuid4()
    chain = [ModelId(primary), ModelId(a), ModelId(b)]
    fb_ids = [str(a), str(b)]
    seen_first: list[UUID] = []
    for _ in range(40):
        result = svc._apply_weighted(
            chain=chain, primary_id=primary, fallback_model_ids=fb_ids
        )
        seen_first.append(UUID(str(result[1])))
    from collections import Counter

    counts = Counter(seen_first)
    # weight 都是 1, 比例应大致 50/50
    assert counts[a] > 0
    assert counts[b] > 0


def test_weighted_skips_zero_or_negative_weight() -> None:
    """weight<=0 的项应被排除, 不会被采样到."""
    svc = _make_svc()
    primary = uuid4()
    a, b = uuid4(), uuid4()
    chain = [ModelId(primary), ModelId(a), ModelId(b)]
    fb_ids = [
        {"id": str(a), "weight": 0},  # 排除
        {"id": str(b), "weight": 1.0},
    ]
    seen_first: list[UUID] = []
    for _ in range(20):
        result = svc._apply_weighted(
            chain=chain, primary_id=primary, fallback_model_ids=fb_ids
        )
        seen_first.append(UUID(str(result[1])))
    from collections import Counter

    counts = Counter(seen_first)
    assert counts[a] == 0
    assert counts[b] == 20


def test_weighted_empty_fallback_falls_back_to_chain() -> None:
    """无 fallback 配 → 返回原 chain (primary 排第一)."""
    svc = _make_svc()
    primary = uuid4()
    a = uuid4()
    chain = [ModelId(primary), ModelId(a)]
    result = svc._apply_weighted(
        chain=chain, primary_id=primary, fallback_model_ids=[]
    )
    # 空 fallback → 原 chain 不变
    assert [UUID(str(m)) for m in result] == [primary, a]


def test_weighted_others_sorted_by_weight_desc() -> None:
    """chosen 排第一, 其余按 weight 降序. 用一个 weight 主导项, 但其他项 sort
    顺序仍要可验证. 我们 seed random 让 chosen 固定 = d (weight 主导), 然后
    验证 '其余' 段降序. 直接用 mock 替 random."""
    svc = _make_svc()
    primary = uuid4()
    a, b, c, d = uuid4(), uuid4(), uuid4(), uuid4()
    chain = [ModelId(primary), ModelId(a), ModelId(b), ModelId(c), ModelId(d)]
    fb_ids = [
        {"id": str(a), "weight": 1.0},
        {"id": str(b), "weight": 2.0},
        {"id": str(c), "weight": 3.0},
        {"id": str(d), "weight": 1.0},
    ]
    # 跑很多次, 每次都验证: result[0]==primary, result[1] 一定在 fallback 里,
    # result[2:] 按 weight 降序 (c > b > a, d 可能在 result[1] 或后面)
    from collections import Counter

    seen_after: list[list[UUID]] = []
    chosen_counter: Counter[UUID] = Counter()
    for _ in range(100):
        result = svc._apply_weighted(
            chain=chain, primary_id=primary, fallback_model_ids=fb_ids
        )
        chosen = UUID(str(result[1]))
        chosen_counter[chosen] += 1
        rest = [UUID(str(m)) for m in result[2:]]
        # 剩余必须按 weight 降序: c(3) > b(2) > a(1), d(1) 与 a 一起
        if c in rest and b in rest:
            assert rest.index(c) < rest.index(b), f"c 应排在 b 前: {rest}"
        if b in rest and a in rest:
            assert rest.index(b) < rest.index(a), f"b 应排在 a 前: {rest}"
        seen_after.append(rest)
    # 至少有一些次 chosen 是 d (a 和 d weight 相同, 但 random 应该 50/50 左右)
    assert chosen_counter[d] > 0
    assert chosen_counter[a] > 0
