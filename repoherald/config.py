"""Configuration loading and validation for RepoHerald."""

from __future__ import annotations

import shutil
from enum import Enum
from pathlib import Path
from typing import Any

import click
import yaml
from pydantic import BaseModel, model_validator

# ─── Constants ────────────────────────────────────────────────────────────────

CONFIG_DIR_NAME = ".repoherald"
CONFIG_FILE_NAME = "config.yaml"
EXAMPLE_CONFIG_NAME = "config.example.yaml"

_PLACEHOLDER_PREFIXES = ("your-",)


def _is_placeholder(value: str) -> bool:
    """Return True if the value looks like an unfilled placeholder."""
    return any(value.startswith(p) for p in _PLACEHOLDER_PREFIXES)


# ─── Pydantic Models ─────────────────────────────────────────────────────────


class LLMProvider(str, Enum):
    openai = "openai"
    claude = "claude"
    gemini = "gemini"
    ollama = "ollama"


class OpenAIConfig(BaseModel):
    api_key: str = ""
    model: str = "gpt-4o"


class ClaudeConfig(BaseModel):
    api_key: str = ""
    model: str = "claude-sonnet-4-20250514"


class GeminiConfig(BaseModel):
    api_key: str = ""
    model: str = "gemini-2.0-flash"


class OllamaConfig(BaseModel):
    host: str = "http://localhost:11434"
    model: str = "llama3.2"


class LLMConfig(BaseModel):
    provider: LLMProvider = LLMProvider.openai
    openai: OpenAIConfig = OpenAIConfig()
    claude: ClaudeConfig = ClaudeConfig()
    gemini: GeminiConfig = GeminiConfig()
    ollama: OllamaConfig = OllamaConfig()


class RedditConfig(BaseModel):
    client_id: str = ""
    client_secret: str = ""
    redirect_uri: str = "http://localhost:8080"
    user_agent: str = "RepoHerald/0.1.0"


class GitHubConfig(BaseModel):
    token: str = ""


class PostingConfig(BaseModel):
    delay_between_posts: int = 10
    post_type: str = "self"


class AppConfig(BaseModel):
    llm: LLMConfig = LLMConfig()
    reddit: RedditConfig = RedditConfig()
    github: GitHubConfig = GitHubConfig()
    posting: PostingConfig = PostingConfig()

    @model_validator(mode="after")
    def validate_llm_credentials(self) -> "AppConfig":
        """Validate LLM credentials at load time (always required)."""
        provider = self.llm.provider
        if provider != LLMProvider.ollama:
            provider_cfg = getattr(self.llm, provider.value)
            api_key: str = provider_cfg.api_key
            if not api_key or _is_placeholder(api_key):
                raise click.ClickException(
                    f"LLM provider '{provider.value}' requires a valid api_key. "
                    f"Set llm.{provider.value}.api_key in your config file."
                )
        return self


# ─── Path Helpers ─────────────────────────────────────────────────────────────


def get_config_dir() -> Path:
    """Return ``~/.repoherald/``, creating it if it doesn't exist."""
    config_dir = Path.home() / CONFIG_DIR_NAME
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_config_path() -> Path:
    """Return the full path to the config file."""
    return get_config_dir() / CONFIG_FILE_NAME


def _find_example_config() -> Path | None:
    """Locate the bundled ``config.example.yaml``."""
    # Check next to the package root (repo root)
    repo_root = Path(__file__).resolve().parent.parent
    candidate = repo_root / EXAMPLE_CONFIG_NAME
    if candidate.exists():
        return candidate
    return None


# ─── Public API ───────────────────────────────────────────────────────────────


def ensure_config_exists() -> None:
    """If no config file exists, copy the example and tell the user to edit it."""
    config_path = get_config_path()
    if config_path.exists():
        return

    example = _find_example_config()
    if example is None:
        raise click.ClickException(
            f"No config file found at {config_path} and no example config to copy.\n"
            f"Please create {config_path} manually."
        )

    shutil.copy2(example, config_path)
    raise click.ClickException(
        f"Created config file at {config_path}\n"
        f"Please edit it with your API keys and credentials, then re-run the command."
    )


def load_config(config_path: Path | None = None) -> AppConfig:
    """Load and validate the YAML configuration.

    Parameters
    ----------
    config_path:
        Explicit path to a config file.  When *None* the default
        ``~/.repoherald/config.yaml`` is used (created from the example
        template if missing).
    """
    if config_path is None:
        ensure_config_exists()
        config_path = get_config_path()

    if not config_path.exists():
        raise click.ClickException(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh) or {}

    return AppConfig.model_validate(raw)


def get_active_llm_config(config: AppConfig) -> dict[str, Any]:
    """Return a plain dict for the currently selected LLM provider.

    The dict always contains ``"provider"`` plus every field defined on
    the provider-specific Pydantic model (e.g. ``api_key``, ``model``).
    """
    provider = config.llm.provider
    provider_cfg = getattr(config.llm, provider.value)
    return {"provider": provider.value, **provider_cfg.model_dump()}


def validate_reddit_config(config: AppConfig) -> None:
    """Validate Reddit credentials. Call before posting (skipped in dry-run)."""
    errors: list[str] = []
    if not config.reddit.client_id or _is_placeholder(config.reddit.client_id):
        errors.append(
            "Reddit client_id is required. "
            "Set reddit.client_id in your config file."
        )
    if not config.reddit.client_secret or _is_placeholder(config.reddit.client_secret):
        errors.append(
            "Reddit client_secret is required. "
            "Set reddit.client_secret in your config file."
        )
    if errors:
        msg = "Reddit configuration errors:\n  • " + "\n  • ".join(errors)
        raise click.ClickException(msg)
