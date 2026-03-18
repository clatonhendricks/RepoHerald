"""OpenAI LLM provider for RepoHerald."""

import logging

import openai

from repoherald.llm.base import LLMProvider, parse_llm_response

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    """Generate Reddit announcements using OpenAI chat models."""

    def __init__(self, api_key: str, model: str = "gpt-4o") -> None:
        self.model = model
        self.client = openai.OpenAI(api_key=api_key)

    def generate(
        self,
        readme_content: str,
        repo_name: str,
        repo_url: str,
        repo_description: str = "",
        repo_language: str = "",
        repo_stars: int = 0,
    ) -> dict:
        messages = self.build_messages(
            readme_content,
            repo_name,
            repo_url,
            repo_description,
            repo_language,
            repo_stars,
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
            )
        except openai.AuthenticationError as exc:
            raise RuntimeError(
                "OpenAI authentication failed — check your API key."
            ) from exc
        except openai.RateLimitError as exc:
            raise RuntimeError(
                "OpenAI rate limit exceeded — try again later."
            ) from exc
        except openai.APIError as exc:
            raise RuntimeError(f"OpenAI API error: {exc}") from exc

        raw_text = response.choices[0].message.content
        logger.debug("OpenAI raw response: %s", raw_text[:500])

        return parse_llm_response(raw_text)
