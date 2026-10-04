"""observability_module — HTTP adapter package."""

from qzdap.modules.observability_module.adapter.http.factory import (
    ObservabilityServiceFactory,
)
from qzdap.modules.observability_module.adapter.http.router import (
    build_router,
    observability_service_dependency,
)

__all__ = [
    "ObservabilityServiceFactory",
    "build_router",
    "observability_service_dependency",
]
