from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from qzdap_llm import LLMClient

from qzdap.modules.model.domain.entities import HealthEvent, Model, Provider, RouteRule


class ModelRepository(ABC):
    @abstractmethod
    async def add(self, model: Model) -> None: ...

    @abstractmethod
    async def get(self, model_id: UUID) -> Model | None: ...

    @abstractmethod
    async def list_for_workspace(self, workspace_id: UUID) -> list[Model]: ...

    @abstractmethod
    async def get_by_upstream_name(
        self, *, workspace_id: UUID, upstream_model: str
    ) -> Model | None:
        """Phase 1: 把 agent 的 upstream 名称解析成 Model (含 id)."""

    @abstractmethod
    async def update(self, model: Model) -> None: ...

    @abstractmethod
    async def delete(self, model_id: UUID) -> None: ...


class ProviderRepository(ABC):
    @abstractmethod
    async def add(self, provider: Provider) -> None: ...

    @abstractmethod
    async def get(self, provider_id: UUID) -> Provider | None: ...

    @abstractmethod
    async def list_for_workspace(self, workspace_id: UUID) -> list[Provider]: ...

    @abstractmethod
    async def update(self, provider: Provider) -> None: ...


class RouteRepository(ABC):
    @abstractmethod
    async def add(self, route: RouteRule) -> None: ...

    @abstractmethod
    async def get(self, route_id: UUID) -> RouteRule | None: ...

    @abstractmethod
    async def list_for_workspace(self, workspace_id: UUID) -> list[RouteRule]: ...

    @abstractmethod
    async def update(self, route: RouteRule) -> None: ...

    @abstractmethod
    async def delete(self, route_id: UUID) -> None: ...


class HealthRepository(ABC):
    @abstractmethod
    async def add(self, event: HealthEvent) -> None: ...

    @abstractmethod
    async def list_for_workspace(
        self, workspace_id: UUID, limit: int = 50
    ) -> list[HealthEvent]: ...


@runtime_checkable
class CredentialCipher(Protocol):
    def encrypt(self, plaintext: bytes, *, aad: bytes | None = None) -> bytes: ...

    def decrypt(self, blob: bytes, *, aad: bytes | None = None) -> bytes: ...

    @property
    def key_version(self) -> int: ...


@runtime_checkable
class ModelClientFactory(Protocol):
    def build(
        self,
        *,
        protocol: str,
        api_key: str,
        base_url: str | None,
        api_version: str = "",
    ) -> LLMClient: ...


class CatalogDiscoveryUnsupported(ValueError):
    """Provider has no supported automatic model-discovery contract."""


class CatalogProber(ABC):
    @abstractmethod
    async def list_models(
        self, *, api_key: str, base_url: str, protocol: str
    ) -> list[str]: ...


class ConnectivityTester(ABC):
    @abstractmethod
    async def test_connection(
        self,
        *,
        api_key: str,
        base_url: str,
        protocol: str,
        model: str,
        api_version: str,
    ) -> dict[str, Any]: ...


__all__ = [
    "CatalogDiscoveryUnsupported",
    "CatalogProber",
    "ConnectivityTester",
    "CredentialCipher",
    "HealthRepository",
    "ModelClientFactory",
    "ModelRepository",
    "ProviderRepository",
    "RouteRepository",
]
