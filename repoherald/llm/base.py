"""Base LLM provider interface and prompt templates for RepoHerald."""

import json
import re
from abc import ABC, abstractmethod

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a developer relations expert who writes engaging Reddit announcements \
for open-source projects. Your goal is to create posts that genuinely inform \
and excite the developer community — not clickbait.

When given information about a GitHub repository you must:

1. **Title** – Write a catchy but professional post title. It should clearly \
convey what the project does and why someone would care. Avoid ALL-CAPS, \
excessive punctuation, or vague hype words.

2. **Body** – Write a 2–3 paragraph post body that:
   - Opens with a concise summary of the problem the project solves.
   - Highlights the key features and practical use cases.
   - Includes the GitHub link so readers can check it out.
   - Ends with an invitation for feedback or contributions.

3. **Subreddits** – Suggest 5–10 relevant, **active** Reddit communities \
where this project would be welcomed. For each subreddit, explain briefly \
why it is a good fit.

Return your response as **valid JSON only** — no markdown fences, no extra \
commentary outside the JSON object.\
"""

USER_PROMPT_TEMPLATE = """\
Please generate a Reddit announcement for the following GitHub repository.

**Repository details:**
- Name: {repo_name}
- URL: {repo_url}
- Description: {repo_description}
- Primary language: {repo_language}
- Stars: {repo_stars}

**README content:**
{readme_content}

Respond with a single JSON object in exactly this format:

{{
  "title": "A concise, engaging post title",
  "body": "The full post body (2-3 paragraphs, include the GitHub link)",
  "subreddits": [
    {{"name": "r/ExampleSubreddit", "reason": "Why this community is relevant"}}
  ]
}}
"""

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

REQUIRED_KEYS = {"title", "body", "subreddits"}


def truncate_readme(content: str, max_chars: int = 8000) -> str:
    """Truncate a README to *max_chars*, appending a notice if trimmed."""
    if len(content) <= max_chars:
        return content
    return content[:max_chars] + "\n\n[README truncated for brevity]"


def parse_llm_response(raw_text: str) -> dict:
    """Extract and validate JSON from an LLM response.

    Handles common quirks such as markdown code fences and leading/trailing
    prose surrounding the JSON payload.

    Returns
    -------
    dict
        A dictionary with at least the keys *title*, *body*, and *subreddits*.

    Raises
    ------
    ValueError
        If the response cannot be parsed or is missing required keys.
    """
    text = raw_text.strip()

    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    fence_pattern = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)
    match = fence_pattern.search(text)
    if match:
        text = match.group(1).strip()

    # Try a direct parse first
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Fall back: find the first top-level { … } block
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if not brace_match:
            raise ValueError(
                "Could not find a JSON object in the LLM response. "
                "Raw response starts with: " + raw_text[:200]
            )
        try:
            data = json.loads(brace_match.group())
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Found a JSON-like block but it is not valid JSON: {exc}. "
                "Raw response starts with: " + raw_text[:200]
            ) from exc

    # Validate required keys
    missing = REQUIRED_KEYS - set(data.keys())
    if missing:
        raise ValueError(
            f"LLM response JSON is missing required key(s): {', '.join(sorted(missing))}. "
            f"Keys found: {', '.join(sorted(data.keys()))}"
        )

    # Light validation on subreddits structure
    if not isinstance(data["subreddits"], list):
        raise ValueError("'subreddits' must be a list of objects, got " + type(data["subreddits"]).__name__)

    return data


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------


class LLMProvider(ABC):
    """Base interface that every LLM provider must implement."""

    @abstractmethod
    def generate(
        self,
        readme_content: str,
        repo_name: str,
        repo_url: str,
        repo_description: str = "",
        repo_language: str = "",
        repo_stars: int = 0,
    ) -> dict:
        """Generate a Reddit announcement for a GitHub repository.

        Parameters
        ----------
        readme_content : str
            The full (or truncated) README text.
        repo_name : str
            Repository name (e.g. ``"owner/repo"``).
        repo_url : str
            Full URL to the repository.
        repo_description : str, optional
            One-line description from GitHub.
        repo_language : str, optional
            Primary programming language.
        repo_stars : int, optional
            Current star count.

        Returns
        -------
        dict
            ``{"title": str, "body": str, "subreddits": [{"name": str, "reason": str}, ...]}``
        """

    def build_messages(
        self,
        readme_content: str,
        repo_name: str,
        repo_url: str,
        repo_description: str = "",
        repo_language: str = "",
        repo_stars: int = 0,
    ) -> list[dict[str, str]]:
        """Build the chat-style message list used by most LLM APIs.

        Subclasses can call this to avoid duplicating prompt-assembly logic.
        """
        user_prompt = USER_PROMPT_TEMPLATE.format(
            repo_name=repo_name,
            repo_url=repo_url,
            repo_description=repo_description or "N/A",
            repo_language=repo_language or "N/A",
            repo_stars=repo_stars,
            readme_content=truncate_readme(readme_content),
        )
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
