"""Domain tests for agent_factory entities (no I/O)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from qzdap_schema.ids import (
    AgentTemplateId,
    AgentVersionId,
    EvalRunId,
    TenantId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.agent_factory.domain.entities import (
    AgentTemplate,
    AgentVersion,
    Release,
)
from qzdap.modules.agent_factory.domain.errors import (
    AgentVersionImmutable,
    AgentVersionInvalidTransition,
)
from qzdap.modules.agent_factory.domain.value_objects import (
    AgentTemplateStatus,
    AgentVersionStatus,
    ReleaseStatus,
)

_TENANT = TenantId(uuid4())
_WORKSPACE = WorkspaceId(uuid4())
_USER = UserId(uuid4())


def _now() -> datetime:
    return datetime(2024, 1, 1, tzinfo=UTC)


def test_template_create_minimal() -> None:
    tpl = AgentTemplate.create(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        name="sales-bot",
        description="FAQ bot",
        default_model_id="default",
        default_system_prompt="hi",
        created_by=_USER,
        now=_now(),
    )
    assert tpl.status is AgentTemplateStatus.ACTIVE
    assert tpl.name == "sales-bot"
    assert tpl.created_at == tpl.updated_at == _now()


def test_template_create_rejects_empty_name() -> None:
    with pytest.raises(ValueError):
        AgentTemplate.create(
            tenant_id=_TENANT,
            workspace_id=_WORKSPACE,
            name="   ",
            description="",
            default_model_id="default",
            default_system_prompt="hi",
            created_by=_USER,
            now=_now(),
        )


def test_template_with_status_round_trips() -> None:
    tpl = AgentTemplate.create(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        name="t",
        description="",
        default_model_id="default",
        default_system_prompt="hi",
        created_by=_USER,
        now=_now(),
    )
    archived = tpl.with_status(AgentTemplateStatus.ARCHIVED, now=_now())
    assert archived.status is AgentTemplateStatus.ARCHIVED
    assert archived.created_at == tpl.created_at


def test_version_create_draft_inherits_template_defaults() -> None:
    tpl = AgentTemplate.create(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        name="t",
        description="",
        default_model_id="gpt-4",
        default_system_prompt="base prompt",
        created_by=_USER,
        now=_now(),
    )
    ver = AgentVersion.create_draft(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        template_id=tpl.id,
        version_tag="1.0.0",
        system_prompt=tpl.default_system_prompt,
        model_id=tpl.default_model_id,
        created_by=_USER,
        now=_now(),
    )
    assert ver.status is AgentVersionStatus.DRAFT
    assert ver.system_prompt == "base prompt"
    assert ver.model_id == "gpt-4"
    assert ver.published_at is None
    assert ver.released_at is None


def test_version_publish_sets_published_at_and_immutable() -> None:
    ver = AgentVersion.create_draft(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        template_id=AgentTemplateId(uuid4()),
        version_tag="1.0.0",
        system_prompt="x",
        model_id="default",
        created_by=_USER,
        now=_now(),
    )
    pub = ver.publish(now=_now())
    assert pub.status is AgentVersionStatus.PUBLISHED
    assert pub.published_at == _now()
    assert pub.is_immutable()
    # re-publish fails
    with pytest.raises(AgentVersionInvalidTransition):
        pub.publish(now=_now())


def test_version_release_only_from_published() -> None:
    ver = AgentVersion.create_draft(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        template_id=AgentTemplateId(uuid4()),
        version_tag="1.0.0",
        system_prompt="x",
        model_id="default",
        created_by=_USER,
        now=_now(),
    )
    # release from draft is not allowed
    with pytest.raises(AgentVersionInvalidTransition):
        ver.release(now=_now())
    pub = ver.publish(now=_now())
    rel = pub.release(now=_now())
    assert rel.status is AgentVersionStatus.RELEASED
    assert rel.released_at == _now()
    # second release fails
    with pytest.raises(AgentVersionInvalidTransition):
        rel.release(now=_now())


def test_version_retire_only_from_released() -> None:
    ver = AgentVersion.create_draft(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        template_id=AgentTemplateId(uuid4()),
        version_tag="1.0.0",
        system_prompt="x",
        model_id="default",
        created_by=_USER,
        now=_now(),
    )
    pub = ver.publish(now=_now())
    rel = pub.release(now=_now())
    ret = rel.retire(now=_now())
    assert ret.status is AgentVersionStatus.RETIRED
    # retire a published version is not allowed
    with pytest.raises(AgentVersionInvalidTransition):
        pub.retire(now=_now())


def test_version_edit_release_notes_only_when_draft() -> None:
    ver = AgentVersion.create_draft(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        template_id=AgentTemplateId(uuid4()),
        version_tag="1.0.0",
        system_prompt="x",
        model_id="default",
        created_by=_USER,
        release_notes="old",
        now=_now(),
    )
    new = ver.with_release_notes("new", now=_now())
    assert new.release_notes == "new"
    pub = new.publish(now=_now())
    # editing after publish is blocked
    with pytest.raises(AgentVersionImmutable):
        pub.with_release_notes("later", now=_now())


def test_release_create_carries_eval_metadata() -> None:
    rel = Release.create(
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        template_id=AgentTemplateId(uuid4()),
        version_id=AgentVersionId(uuid4()),
        eval_run_id=EvalRunId(uuid4()),
        eval_score=0.83,
        released_by=_USER,
        notes="GA",
        now=_now(),
    )
    assert rel.status is ReleaseStatus.RELEASED
    assert rel.eval_score == 0.83
    assert rel.released_at == _now()


__all__ = []
