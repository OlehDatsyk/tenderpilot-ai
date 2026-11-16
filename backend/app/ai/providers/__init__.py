from app.ai.base import AIConfig, AINotConfiguredError, ProviderAdapter
from app.ai.providers.anthropic_provider import AnthropicAdapter
from app.ai.providers.http_providers import GeminiAdapter, OpenAIAdapter

_ADAPTERS: dict[str, ProviderAdapter] = {
    "anthropic": AnthropicAdapter(),
    "openai": OpenAIAdapter(),
    "gemini": GeminiAdapter(),
}


def get_adapter(config: AIConfig) -> ProviderAdapter:
    adapter = _ADAPTERS.get(config.provider)
    if adapter is None:
        raise AINotConfiguredError("No AI provider is configured.")
    return adapter


def register_adapter(name: str, adapter: ProviderAdapter) -> None:
    """Used by tests to install a mocked provider."""
    _ADAPTERS[name] = adapter
