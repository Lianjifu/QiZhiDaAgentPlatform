"""Development requests fail instead of executing mock provider behavior."""

import pytest
from qzdap_llm.client import ChatRequest
from qzdap_llm.mock import MockLLMClient

from qzdap.composition.container import Container
from qzdap.composition.settings import Settings
from qzdap.composition.unavailable_providers import ProviderUnavailable


@pytest.mark.asyncio
async def test_development_rejects_mock_provider_invocations() -> None:
    container = Container(Settings(env="development", llm_provider="mock", embedding_provider="noop"))
    client = container.llm_client()
    request = ChatRequest(model="test", messages=[])
    with pytest.raises(ProviderUnavailable):
        await client.chat(request)
    with pytest.raises(ProviderUnavailable):
        async for _ in client.stream(request):
            pytest.fail("development must not return mock chunks")
    with pytest.raises(ProviderUnavailable):
        await client.embed(["test"])
    with pytest.raises(ProviderUnavailable):
        await container.memory_embedding_adapter().embed(["test"])


def test_test_environment_can_explicitly_use_mock_provider() -> None:
    container = Container(Settings(env="test", llm_provider="mock", embedding_provider="noop"))
    assert isinstance(container.llm_client(), MockLLMClient)
