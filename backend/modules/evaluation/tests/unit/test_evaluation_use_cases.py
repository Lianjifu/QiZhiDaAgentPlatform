"""**评测的「列用例」用例 + 真跑评测那条路的取值** ✓。

⚠️ **这两个都是 P-13 的 mypy 扫出来的真缺陷** ✓（潜伏的运行时错误 ✓）：

- `EvaluationService` **没有** `list_cases` ✓ —— 而 `GET /datasets/{did}/cases`
  直接取 `svc.list_cases` ✓ → **那个端点必然 500** ✓；
- `RealSubAgentPort` 拿到的版本是**字典** ✓，却按**属性**访问 ✓
  （`version.default_model_id` ✓ —— 那个属性连领域对象上都没有 ✓ —— 领域里叫
  `model_id` ✓）→ `AttributeError` ✓；而且**根本没有任何人实现
  `AgentFactoryQueryPort`** ✓ → 那条路一走就炸 ✓。

验收 ✓：
- **服务上确实有这个用例** ✓，列得出用例 ✓；
- **按键取值** ✓ —— 版本号与模型 id 都从字典里正确取到 ✓。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from _evaluation_unit_in_memory import (  # type: ignore[import-not-found]
    InMemoryEvalDatasetRepository,
    InMemoryEvalRunRepository,
    make_case,
    make_dataset,
)

from qzdap.modules.evaluation.adapter.sub_agent_real import RealSubAgentPort
from qzdap.modules.evaluation.application.services import EvaluationService
from qzdap_kernel.ids import (
    AgentTemplateId,
    AgentVersionId,
    EvalDatasetId,
    TenantId,
    UserId,
    WorkspaceId,
)

_TENANT = TenantId(uuid4())
_WORKSPACE = WorkspaceId(uuid4())
_USER = UserId(uuid4())


def _service(repo: InMemoryEvalDatasetRepository) -> EvaluationService:
    return EvaluationService.from_parts(
        dataset_repository=repo,
        run_repository=InMemoryEvalRunRepository(),
        runner=cast("Any", object()),
    )


@pytest.mark.asyncio
async def test_the_service_exposes_the_case_listing_use_case() -> None:
    """**服务上有 `list_cases`** ✓（之前没有 ✓ → 端点必然 500 ✓）。"""
    repo = InMemoryEvalDatasetRepository()
    dataset = make_dataset()
    case = make_case(
        dataset_id=EvalDatasetId(dataset.id),
        tenant_id=TenantId(dataset.tenant_id),
        workspace_id=WorkspaceId(dataset.workspace_id),
        ordinal=0,
        input="你好",
    )
    await repo.add(dataset)
    await repo.add_case(case)

    svc = _service(repo)

    assert svc.list_cases is not None, "服务上必须挂上 list_cases 用例"
    rows = await svc.list_cases.execute(
        tenant_id=TenantId(dataset.tenant_id),
        dataset_id=EvalDatasetId(dataset.id),
    )
    assert [row.input for row in rows] == ["你好"]


class _RecordingOneShot:
    """**记录调用参数** ✓ —— 断言取值对不对 ✓。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def run(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        completion = SimpleNamespace(
            final_message="答复",
            turn_id=uuid4(),
            input_tokens=3,
            output_tokens=5,
        )
        return SimpleNamespace(completion=completion)


class _FakeAgentFactory:
    """**按端口的契约返回字典** ✓。"""

    def __init__(self, version: dict[str, Any] | None) -> None:
        self._version = version

    async def get_agent_version(
        self,
        *,
        tenant_id: TenantId,
        template_id: AgentTemplateId,
        version_id: AgentVersionId,
    ) -> dict[str, Any] | None:
        return self._version


@pytest.mark.asyncio
async def test_the_real_sub_agent_reads_the_version_by_key() -> None:
    """**按键取值** ✓ —— 版本号与模型 id ✓（之前按属性访问字典 ✓ → 必炸 ✓）。"""
    one_shot = _RecordingOneShot()
    port = RealSubAgentPort(
        one_shot=cast("Any", one_shot),
        agent_factory=_FakeAgentFactory(
            {"model_id": "model-1", "version_tag": "v3", "status": "published"}
        ),
    )

    result = await port.run_turn_to_completion(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        owner_id=_USER,
        agent_id=AgentTemplateId(uuid4()),
        agent_version=str(uuid4()),
        user_input="你好",
        timeout_seconds=5,
    )

    assert result["final_message"] == "答复"
    assert one_shot.calls[0]["agent_version"] == "v3"
    assert one_shot.calls[0]["model"] == "model-1"


@pytest.mark.asyncio
async def test_the_real_sub_agent_fails_loudly_when_the_version_is_missing() -> None:
    """**版本不在就明确报错** ✓（不拿空值继续跑 ✓）。"""
    from qzdap_kernel.errors import AppError

    port = RealSubAgentPort(
        one_shot=cast("Any", _RecordingOneShot()),
        agent_factory=_FakeAgentFactory(None),
    )

    with pytest.raises(AppError):
        await port.run_turn_to_completion(
            tenant_id=_TENANT,
            workspace_id=_WORKSPACE,
            owner_id=_USER,
            agent_id=AgentTemplateId(uuid4()),
            agent_version=str(uuid4()),
            user_input="你好",
            timeout_seconds=5,
        )
