"""Ollama (local) LLM provider for RepoHerald."""

from ollama import Client, ResponseError

from repoherald.llm.base import LLMProvider, parse_llm_response


class OllamaProvider(LLMProvider):
    """Generate Reddit announcements using a local Ollama instance."""

    def __init__(
        self, host: str = "http://localhost:11434", model: str = "llama3.2"
    ) -> None:
        self.host = host
        self.model = model
        self.client = Client(host=host)

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
            readme_content=readme_content,
            repo_name=repo_name,
            repo_url=repo_url,
            repo_description=repo_description,
            repo_language=repo_language,
            repo_stars=repo_stars,
        )

        try:
            response = self.client.chat(
                model=self.model, messages=messages, format="json"
            )
        except ConnectionError as exc:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self.host}. "
                "Make sure Ollama is running."
            ) from exc
        except ResponseError as exc:
            if "not found" in str(exc).lower():
                raise RuntimeError(
                    f"Model '{self.model}' not found in Ollama. "
                    f"Pull it first with: ollama pull {self.model}"
                ) from exc
            raise

        raw_text = response["message"]["content"]
        return parse_llm_response(raw_text)
