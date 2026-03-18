"""LLM provider package."""

from __future__ import annotations

from repoherald.config import AppConfig, LLMProvider as LLMProviderEnum
from repoherald.llm.base import LLMProvider


def create_provider(config: AppConfig) -> LLMProvider:
    """Create the appropriate LLM provider from the application config.

    Reads ``config.llm.provider`` and instantiates the matching class with
    the provider-specific settings (API key / host, model name).

    Returns
    -------
    LLMProvider
        A ready-to-use provider instance.

    Raises
    ------
    ValueError
        If the configured provider name is not recognised.
    """
    provider = config.llm.provider

    if provider == LLMProviderEnum.openai:
        from repoherald.llm.openai_provider import OpenAIProvider

        cfg = config.llm.openai
        return OpenAIProvider(api_key=cfg.api_key, model=cfg.model)

    if provider == LLMProviderEnum.claude:
        from repoherald.llm.claude_provider import ClaudeProvider

        cfg = config.llm.claude
        return ClaudeProvider(api_key=cfg.api_key, model=cfg.model)

    if provider == LLMProviderEnum.gemini:
        from repoherald.llm.gemini_provider import GeminiProvider

        cfg = config.llm.gemini
        return GeminiProvider(api_key=cfg.api_key, model=cfg.model)

    if provider == LLMProviderEnum.ollama:
        from repoherald.llm.ollama_provider import OllamaProvider

        cfg = config.llm.ollama
        return OllamaProvider(host=cfg.host, model=cfg.model)

    raise ValueError(f"Unknown LLM provider: {provider!r}")
