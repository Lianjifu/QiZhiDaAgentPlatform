"""AgentFactoryService — composition root for agent_factory use cases.

Mirrors :class:`KnowledgeService` / :class:`OrchestrationService` —
``from_parts`` is the factory the composition root uses to wire the
per-request session.
"""

from __future__ import annotations

from dataclasses import dataclass

from qzdap.modules.agent_factory.application.ports import (
    AgentFactoryEventPublisher,
    AgentTemplateRepository,
    AgentVersionRepository,
    EvaluationQueryPort,
    ReleaseRepository,
)
from qzdap.modules.agent_factory.application.use_cases.create_template import (
    CreateAgentTemplateUseCase,
)
from qzdap.modules.agent_factory.application.use_cases.create_version import (
    CreateAgentVersionUseCase,
)
from qzdap.modules.agent_factory.application.use_cases.get_release import (
    GetReleaseUseCase,
    ListReleasesUseCase,
)
from qzdap.modules.agent_factory.application.use_cases.get_template import (
    GetAgentTemplateUseCase,
)
from qzdap.modules.agent_factory.application.use_cases.get_version import (
    GetAgentVersionUseCase,
)
from qzdap.modules.agent_factory.application.use_cases.list_templates import (
    ListAgentTemplatesUseCase,
)
from qzdap.modules.agent_factory.application.use_cases.list_versions import (
    ListAgentVersionsUseCase,
)
from qzdap.modules.agent_factory.application.use_cases.publish_version import (
    PublishAgentVersionUseCase,
)
from qzdap.modules.agent_factory.application.use_cases.release_version import (
    ReleaseAgentVersionUseCase,
)
from qzdap.modules.agent_factory.application.use_cases.retire_version import (
    RetireAgentVersionUseCase,
)
from qzdap.modules.agent_factory.application.use_cases.update_template import (
    UpdateAgentTemplateUseCase,
)
from qzdap.modules.agent_factory.application.use_cases.update_version_notes import (
    UpdateAgentVersionNotesUseCase,
)


@dataclass(slots=True)
class AgentFactoryService:
    template_repository: AgentTemplateRepository
    version_repository: AgentVersionRepository
    release_repository: ReleaseRepository
    evaluation_query: EvaluationQueryPort
    publisher: AgentFactoryEventPublisher | None = None
    policy_guard: object | None = None
    eval_score_min: float = 0.6

    create_template: CreateAgentTemplateUseCase | None = None
    get_template: GetAgentTemplateUseCase | None = None
    list_templates: ListAgentTemplatesUseCase | None = None
    update_template: UpdateAgentTemplateUseCase | None = None
    create_version: CreateAgentVersionUseCase | None = None
    get_version: GetAgentVersionUseCase | None = None
    list_versions: ListAgentVersionsUseCase | None = None
    update_version_notes: UpdateAgentVersionNotesUseCase | None = None
    publish_version: PublishAgentVersionUseCase | None = None
    release_version: ReleaseAgentVersionUseCase | None = None
    retire_version: RetireAgentVersionUseCase | None = None
    get_release: GetReleaseUseCase | None = None
    list_releases: ListReleasesUseCase | None = None

    def __post_init__(self) -> None:
        self.create_template = CreateAgentTemplateUseCase(
            repository=self.template_repository,
            publisher=self.publisher,
            policy_guard=self.policy_guard,
        )
        self.get_template = GetAgentTemplateUseCase(
            repository=self.template_repository,
        )
        self.list_templates = ListAgentTemplatesUseCase(
            repository=self.template_repository,
        )
        self.update_template = UpdateAgentTemplateUseCase(
            repository=self.template_repository,
            publisher=self.publisher,
            policy_guard=self.policy_guard,
        )
        self.create_version = CreateAgentVersionUseCase(
            template_repository=self.template_repository,
            version_repository=self.version_repository,
            publisher=self.publisher,
            policy_guard=self.policy_guard,
        )
        self.get_version = GetAgentVersionUseCase(
            repository=self.version_repository,
        )
        self.list_versions = ListAgentVersionsUseCase(
            repository=self.version_repository,
        )
        self.update_version_notes = UpdateAgentVersionNotesUseCase(
            repository=self.version_repository,
        )
        self.publish_version = PublishAgentVersionUseCase(
            repository=self.version_repository,
            publisher=self.publisher,
            policy_guard=self.policy_guard,
        )
        self.release_version = ReleaseAgentVersionUseCase(
            template_repository=self.template_repository,
            version_repository=self.version_repository,
            release_repository=self.release_repository,
            evaluation_query=self.evaluation_query,
            publisher=self.publisher,
            policy_guard=self.policy_guard,
            eval_score_min=self.eval_score_min,
        )
        self.retire_version = RetireAgentVersionUseCase(
            repository=self.version_repository,
        )
        self.get_release = GetReleaseUseCase(
            repository=self.release_repository,
        )
        self.list_releases = ListReleasesUseCase(
            repository=self.release_repository,
        )

    # ---- factory --------------------------------------------------------

    @classmethod
    def from_parts(
        cls,
        *,
        template_repository: AgentTemplateRepository,
        version_repository: AgentVersionRepository,
        release_repository: ReleaseRepository,
        evaluation_query: EvaluationQueryPort,
        publisher: AgentFactoryEventPublisher | None = None,
        policy_guard: object | None = None,
        eval_score_min: float = 0.6,
    ) -> AgentFactoryService:
        return cls(
            template_repository=template_repository,
            version_repository=version_repository,
            release_repository=release_repository,
            evaluation_query=evaluation_query,
            publisher=publisher,
            policy_guard=policy_guard,
            eval_score_min=eval_score_min,
        )


__all__ = ["AgentFactoryService"]
