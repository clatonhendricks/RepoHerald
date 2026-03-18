"""Anthropic Claude LLM provider for RepoHerald."""

import anthropic

from repoherald.llm.base import LLMProvider, parse_llm_response


class ClaudeProvider(LLMProvider):
    """Generate Reddit announcements using Anthropic's Claude API."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514") -> None:
        self.model = model
        self.client = anthropic.Anthropic(api_key=api_key)

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
            readme_content, repo_name, repo_url,
            repo_description, repo_language, repo_stars,
        )

        # Anthropic takes system as a separate parameter
        system_text = messages[0]["content"]
        user_messages = [{"role": m["role"], "content": m["content"]} for m in messages[1:]]

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system_text,
                messages=user_messages,
            )
        except anthropic.APIError as exc:
            raise RuntimeError(f"Claude API error: {exc}") from exc

        raw_text = response.content[0].text
        return parse_llm_response(raw_text)
