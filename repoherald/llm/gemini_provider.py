"""Google Gemini LLM provider for RepoHerald."""

import google.generativeai as genai

from repoherald.llm.base import SYSTEM_PROMPT, LLMProvider, parse_llm_response


class GeminiProvider(LLMProvider):
    """Generate Reddit announcements using Google's Gemini API."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(
            model_name=model,
            system_instruction=SYSTEM_PROMPT,
        )

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
        # Gemini receives the system instruction at model level;
        # only the user message is passed to generate_content.
        user_prompt = messages[1]["content"]

        try:
            response = self._model.generate_content(
                user_prompt,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                ),
            )
            return parse_llm_response(response.text)
        except genai.types.BlockedPromptException as exc:
            raise RuntimeError(
                "Gemini blocked the prompt due to safety filters."
            ) from exc
        except genai.types.StopCandidateException as exc:
            raise RuntimeError(
                "Gemini stopped generating early — the response may have "
                "been flagged by safety filters."
            ) from exc
        except Exception as exc:
            raise RuntimeError(
                f"Gemini API request failed: {exc}"
            ) from exc
