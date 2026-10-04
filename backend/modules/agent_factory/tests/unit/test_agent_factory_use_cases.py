"""Application tests for agent_factory use cases (in-memory fakes)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from _agent_factory_unit_in_memory import (  # type: ignore[import-not-found]
    InMemoryAgentTemplateRepository,
    InMemoryAgentVersionRepository,
    InMemoryEvaluationQuery,
    InMemoryReleaseRepository,
    RecordingPublisher,
    make_eval_summary,
)
from qzdap_kernel.errors import BusinessRuleError
from qzdap_schema.ids import (
    AgentTemplateId,
    AgentVersionId,
    EvalRunId,
    TenantId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.agent_factory.application.services import AgentFactoryService
from qzdap.modules.agent_factory.domain.errors import (
    AgentFactoryError,
    AgentTemplateNameConflict,
    AgentTemplateNotFound,
    AgentVersionImmutable,
    AgentVersionNotFound,
    AgentVersionTagConflict,
)
from qzdap.modules.agent_factory.domain.value_objects import (
    AgentVersionStatus,
)

_TENANT = TenantId(uuid4())
_WORKSPACE = WorkspaceId(uuid4())
_USER = UserId(uuid4())


def _service(**overrides):  # type: ignore[no-untyped-def]
    tpl_repo = InMemoryAgentTemplateRepository()
    ver_repo = InMemoryAgentVersionRepository()
    rel_repo = InMemoryReleaseRepository()
    eval_q = InMemoryEvaluationQuery()
    pub = RecordingPublisher()
    svc = AgentFactoryService.from_parts(
        template_repository=tpl_repo,
        version_repository=ver_repo,
        release_repository=rel_repo,
        evaluation_query=eval_q,
        publisher=pub,
        policy_guard=None,
        eval_score_min=0.6,
        **overrides,
    )
    return svc, tpl_repo, ver_repo, rel_repo, eval_q, pub


@pytest.mark.asyncio
async def test_create_template_persists_and_publishes_event() -> None:
    svc, *_ = _service()
    tpl = await svc.create_template.execute(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        name="sales-bot",
        description="FAQ bot",
        default_model_id="default",
        default_system_prompt="hi",
        created_by=_USER,
    )
    assert tpl.name == "sales-bot"
    assert len(_service()[5].published) == 0  # not used
    _, _, _, _, _, _pub = _service()  # fresh publisher above wouldn't have event
    # Re-run to assert publisher side-effect:
    svc2, *_ = _service()
    await svc2.create_template.execute(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        name="sales-bot-2",
        description="",
        default_model_id="default",
        default_system_prompt="hi",
        created_by=_USER,
    )
    assert any(
        getattr(e, "TOPIC", "") == "agent_factory.template.created"
        for e in svc2.create_template.publisher.published
    )


@pytest.mark.asyncio
async def test_create_template_name_conflict_409() -> None:
    svc, *_ = _service()
    await svc.create_template.execute(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        name="dup",
        description="",
        default_model_id="default",
        default_system_prompt="hi",
        created_by=_USER,
    )
    with pytest.raises(AgentTemplateNameConflict):
        await svc.create_template.execute(
            tenant_id=_TENANT,
            workspace_id=_WORKSPACE,
            name="dup",
            description="",
            default_model_id="default",
            default_system_prompt="hi",
            created_by=_USER,
        )


@pytest.mark.asyncio
async def test_create_version_inherits_template_defaults() -> None:
    svc, _tpl_repo, *_ = _service()
    tpl = await svc.create_template.execute(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        name="t",
        description="",
        default_model_id="gpt-4",
        default_system_prompt="base",
        created_by=_USER,
    )
    ver = await svc.create_version.execute(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        template_id=tpl.id,
        version_tag="1.0.0",
        created_by=_USER,
    )
    assert ver.system_prompt == "base"
    assert ver.model_id == "gpt-4"
    assert ver.status is AgentVersionStatus.DRAFT


@pytest.mark.asyncio
async def test_create_version_tag_conflict_409() -> None:
    svc, _tpl_repo, *_ = _service()
    tpl = await svc.create_template.execute(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        name="t",
        description="",
        default_model_id="default",
        default_system_prompt="hi",
        created_by=_USER,
    )
    await svc.create_version.execute(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        template_id=tpl.id,
        version_tag="1.0.0",
        created_by=_USER,
    )
    with pytest.raises(AgentVersionTagConflict):
        await svc.create_version.execute(
            tenant_id=_TENANT,
            workspace_id=_WORKSPACE,
            template_id=tpl.id,
            version_tag="1.0.0",
            created_by=_USER,
        )


@pytest.mark.asyncio
async def test_create_version_unknown_template_404() -> None:
    svc, *_ = _service()
    with pytest.raises(AgentTemplateNotFound):
        await svc.create_version.execute(
            tenant_id=_TENANT,
            workspace_id=_WORKSPACE,
            template_id=AgentTemplateId(uuid4()),
            version_tag="1.0.0",
            created_by=_USER,
        )


@pytest.mark.asyncio
async def test_publish_then_release_with_eval_passes_gate() -> None:
    svc, _, _, _, eval_q, pub = _service()
    tpl = await svc.create_template.execute(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        name="t",
        description="",
        default_model_id="default",
        default_system_prompt="hi",
        created_by=_USER,
    )
    ver = await svc.create_version.execute(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        template_id=tpl.id,
        version_tag="1.0.0",
        created_by=_USER,
    )
    pub_ver = await svc.publish_version.execute(tenant_id=_TENANT, version_id=ver.id)
    assert pub_ver.status is AgentVersionStatus.PUBLISHED
    # seed a passing eval
    eval_q.add(
        tenant_id=_TENANT,
        template_id=tpl.id,
        version_id=pub_ver.id,
        summary=make_eval_summary(
            run_id=EvalRunId(uuid4()), status="passed", mean_score=0.85
        ),
    )
    rel = await svc.release_version.execute(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        template_id=tpl.id,
        version_id=pub_ver.id,
        released_by=_USER,
        notes="GA",
    )
    assert rel.eval_score == 0.85
    # version flipped to RELEASED
    fresh = await svc.get_version.execute(tenant_id=_TENANT, version_id=pub_ver.id)
    assert fresh.status is AgentVersionStatus.RELEASED
    # event published
    assert any(
        getattr(e, "TOPIC", "") == "agent_factory.version.released"
        for e in pub.published
    )


@pytest.mark.asyncio
async def test_release_without_eval_returns_422() -> None:
    svc, *_ = _service()
    tpl = await svc.create_template.execute(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        name="t",
        description="",
        default_model_id="default",
        default_system_prompt="hi",
        created_by=_USER,
    )
    ver = await svc.create_version.execute(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        template_id=tpl.id,
        version_tag="1.0.0",
        created_by=_USER,
    )
    pub_ver = await svc.publish_version.execute(tenant_id=_TENANT, version_id=ver.id)
    with pytest.raises(BusinessRuleError) as exc:
        await svc.release_version.execute(
            tenant_id=_TENANT,
            workspace_id=_WORKSPACE,
            template_id=tpl.id,
            version_id=pub_ver.id,
        )
    assert exc.value.code == "EVAL_GATE_FAILED"
    assert exc.value.status == 422


@pytest.mark.asyncio
async def test_release_with_below_threshold_returns_422() -> None:
    svc, _, _, _, eval_q, _ = _service()
    tpl = await svc.create_template.execute(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        name="t",
        description="",
        default_model_id="default",
        default_system_prompt="hi",
        created_by=_USER,
    )
    ver = await svc.create_version.execute(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        template_id=tpl.id,
        version_tag="1.0.0",
        created_by=_USER,
    )
    pub_ver = await svc.publish_version.execute(tenant_id=_TENANT, version_id=ver.id)
    eval_q.add(
        tenant_id=_TENANT,
        template_id=tpl.id,
        version_id=pub_ver.id,
        summary=make_eval_summary(
            run_id=EvalRunId(uuid4()), status="passed", mean_score=0.4
        ),
    )
    with pytest.raises(BusinessRuleError) as exc:
        await svc.release_version.execute(
            tenant_id=_TENANT,
            workspace_id=_WORKSPACE,
            template_id=tpl.id,
            version_id=pub_ver.id,
        )
    assert exc.value.code == "EVAL_GATE_FAILED"


@pytest.mark.asyncio
async def test_release_with_failed_status_returns_422() -> None:
    svc, _, _, _, eval_q, _ = _service()
    tpl = await svc.create_template.execute(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        name="t",
        description="",
        default_model_id="default",
        default_system_prompt="hi",
        created_by=_USER,
    )
    ver = await svc.create_version.execute(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        template_id=tpl.id,
        version_tag="1.0.0",
        created_by=_USER,
    )
    pub_ver = await svc.publish_version.execute(tenant_id=_TENANT, version_id=ver.id)
    # score ok but status=failed → gate refuses
    eval_q.add(
        tenant_id=_TENANT,
        template_id=tpl.id,
        version_id=pub_ver.id,
        summary=make_eval_summary(
            run_id=EvalRunId(uuid4()), status="failed", mean_score=0.9
        ),
    )
    with pytest.raises(BusinessRuleError) as exc:
        await svc.release_version.execute(
            tenant_id=_TENANT,
            workspace_id=_WORKSPACE,
            template_id=tpl.id,
            version_id=pub_ver.id,
        )
    assert exc.value.code == "EVAL_GATE_FAILED"


@pytest.mark.asyncio
async def test_release_unpublished_version_returns_422() -> None:
    svc, _, _, _, eval_q, _ = _service()
    tpl = await svc.create_template.execute(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        name="t",
        description="",
        default_model_id="default",
        default_system_prompt="hi",
        created_by=_USER,
    )
    ver = await svc.create_version.execute(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        template_id=tpl.id,
        version_tag="1.0.0",
        created_by=_USER,
    )
    # even with passing eval, draft cannot be released
    eval_q.add(
        tenant_id=_TENANT,
        template_id=tpl.id,
        version_id=ver.id,
        summary=make_eval_summary(
            run_id=EvalRunId(uuid4()), status="passed", mean_score=0.9
        ),
    )
    with pytest.raises(BusinessRuleError) as exc:
        await svc.release_version.execute(
            tenant_id=_TENANT,
            workspace_id=_WORKSPACE,
            template_id=tpl.id,
            version_id=ver.id,
        )
    assert exc.value.code == "EVAL_GATE_FAILED"


@pytest.mark.asyncio
async def test_update_release_notes_only_while_draft() -> None:
    svc, *_ = _service()
    tpl = await svc.create_template.execute(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        name="t",
        description="",
        default_model_id="default",
        default_system_prompt="hi",
        created_by=_USER,
    )
    ver = await svc.create_version.execute(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        template_id=tpl.id,
        version_tag="1.0.0",
        created_by=_USER,
    )
    upd = await svc.update_version_notes.execute(
        tenant_id=_TENANT, version_id=ver.id, release_notes="initial"
    )
    assert upd.release_notes == "initial"
    # publish → editing notes must fail
    await svc.publish_version.execute(tenant_id=_TENANT, version_id=ver.id)
    with pytest.raises(AgentVersionImmutable):
        await svc.update_version_notes.execute(
            tenant_id=_TENANT, version_id=ver.id, release_notes="later"
        )


@pytest.mark.asyncio
async def test_retire_only_after_release() -> None:
    svc, *_ = _service()
    tpl = await svc.create_template.execute(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        name="t",
        description="",
        default_model_id="default",
        default_system_prompt="hi",
        created_by=_USER,
    )
    ver = await svc.create_version.execute(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        template_id=tpl.id,
        version_tag="1.0.0",
        created_by=_USER,
    )
    # retire on draft must fail
    with pytest.raises(AgentFactoryError):
        await svc.retire_version.execute(tenant_id=_TENANT, version_id=ver.id)


@pytest.mark.asyncio
async def test_get_unknown_version_404() -> None:
    svc, *_ = _service()
    with pytest.raises(AgentVersionNotFound):
        await svc.get_version.execute(
            tenant_id=_TENANT, version_id=AgentVersionId(uuid4())
        )


@pytest.mark.asyncio
async def test_list_templates_filters_workspace() -> None:
    svc, *_ = _service()
    ws_a = WorkspaceId(uuid4())
    ws_b = WorkspaceId(uuid4())
    await svc.create_template.execute(
        tenant_id=_TENANT,
        workspace_id=ws_a,
        name="a1",
        description="",
        default_model_id="default",
        default_system_prompt="hi",
        created_by=_USER,
    )
    await svc.create_template.execute(
        tenant_id=_TENANT,
        workspace_id=ws_b,
        name="b1",
        description="",
        default_model_id="default",
        default_system_prompt="hi",
        created_by=_USER,
    )
    rows_a = await svc.list_templates.execute(tenant_id=_TENANT, workspace_id=ws_a)
    rows_b = await svc.list_templates.execute(tenant_id=_TENANT, workspace_id=ws_b)
    assert {t.name for t in rows_a} == {"a1"}
    assert {t.name for t in rows_b} == {"b1"}


__all__ = []
