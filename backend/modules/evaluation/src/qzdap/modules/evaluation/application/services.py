"""EvaluationService — composition root for evaluation use cases."""

from __future__ import annotations

from dataclasses import dataclass

from qzdap.modules.evaluation.application.ports import (
    EvalDatasetRepository,
    EvalRunRepository,
)
from qzdap.modules.evaluation.application.runner import EvalRunner
from qzdap.modules.evaluation.application.use_cases.get_dataset import (
    GetEvalDatasetUseCase,
    ListEvalDatasetsUseCase,
)
from qzdap.modules.evaluation.application.use_cases.get_run import (
    GetEvalRunUseCase,
    ListEvalRunsUseCase,
)
from qzdap.modules.evaluation.application.use_cases.start_run import (
    StartEvalRunUseCase,
)


@dataclass(slots=True)
class EvaluationService:
    dataset_repository: EvalDatasetRepository
    run_repository: EvalRunRepository
    runner: EvalRunner
    publisher: object | None = None
    policy_guard: object | None = None
    eval_score_min: float = 0.6

    get_dataset: GetEvalDatasetUseCase | None = None
    list_datasets: ListEvalDatasetsUseCase | None = None
    get_run: GetEvalRunUseCase | None = None
    list_runs: ListEvalRunsUseCase | None = None
    start_run: StartEvalRunUseCase | None = None

    def __post_init__(self) -> None:
        self.get_dataset = GetEvalDatasetUseCase(repository=self.dataset_repository)
        self.list_datasets = ListEvalDatasetsUseCase(repository=self.dataset_repository)
        self.get_run = GetEvalRunUseCase(repository=self.run_repository)
        self.list_runs = ListEvalRunsUseCase(repository=self.run_repository)
        self.start_run = StartEvalRunUseCase(
            dataset_repo=self.dataset_repository,
            run_repo=self.run_repository,
            runner=self.runner,
            policy_guard=self.policy_guard,
        )

    @classmethod
    def from_parts(
        cls,
        *,
        dataset_repository: EvalDatasetRepository,
        run_repository: EvalRunRepository,
        runner: EvalRunner,
        publisher: object | None = None,
        policy_guard: object | None = None,
        eval_score_min: float = 0.6,
    ) -> EvaluationService:
        return cls(
            dataset_repository=dataset_repository,
            run_repository=run_repository,
            runner=runner,
            publisher=publisher,
            policy_guard=policy_guard,
            eval_score_min=eval_score_min,
        )


__all__ = ["EvaluationService"]
