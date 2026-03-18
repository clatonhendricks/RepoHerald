"""Fetch GitHub repository README and metadata via the REST API."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import requests

# Matches full GitHub URLs, with or without scheme, optional .git / tree / blob suffixes
_GITHUB_URL_RE = re.compile(
    r"^(?:https?://)?github\.com/"
    r"(?P<owner>[A-Za-z0-9\-_.]+)/"
    r"(?P<repo>[A-Za-z0-9\-_.]+?)"
    r"(?:\.git)?(?:/.*)?$"
)

# Matches the bare owner/repo shorthand (no slashes beyond the separator)
_SHORTHAND_RE = re.compile(
    r"^(?P<owner>[A-Za-z0-9\-_.]+)/(?P<repo>[A-Za-z0-9\-_.]+)$"
)

_API_BASE = "https://api.github.com"


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclass
class RepoInfo:
    """Lightweight container for repository metadata + README content."""

    owner: str
    name: str
    description: str
    stars: int
    language: str
    topics: list[str] = field(default_factory=list)
    readme_content: str = ""
    url: str = ""


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------

def parse_github_url(url: str) -> tuple[str, str]:
    """Extract *owner* and *repo* from a GitHub URL or ``owner/repo`` shorthand.

    Returns:
        A ``(owner, repo)`` tuple.

    Raises:
        ValueError: If the string doesn't look like a valid GitHub reference.
    """
    url = url.strip()

    match = _GITHUB_URL_RE.match(url)
    if match:
        return match.group("owner"), match.group("repo")

    match = _SHORTHAND_RE.match(url)
    if match:
        return match.group("owner"), match.group("repo")

    raise ValueError(
        f"[bold red]Cannot parse GitHub URL:[/bold red] {url!r}\n"
        "Expected formats: https://github.com/owner/repo, github.com/owner/repo, or owner/repo"
    )


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _build_headers(token: str | None = None, *, raw: bool = False) -> dict[str, str]:
    """Build request headers, optionally with auth and raw-content accept."""
    headers: dict[str, str] = {"X-GitHub-Api-Version": "2022-11-28"}
    if raw:
        headers["Accept"] = "application/vnd.github.raw+json"
    else:
        headers["Accept"] = "application/vnd.github+json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _handle_response_errors(resp: requests.Response, context: str) -> None:
    """Raise a friendly error for common GitHub API failure codes."""
    if resp.status_code == 404:
        raise FileNotFoundError(
            f"[bold red]{context} not found.[/bold red] "
            "Check that the repository exists and is not private."
        )
    if resp.status_code == 403:
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if "rate limit" in body.get("message", "").lower():
            raise PermissionError(
                "[bold yellow]GitHub API rate limit exceeded.[/bold yellow] "
                "Add a GitHub personal-access token in your config to raise the limit "
                "(from 60 → 5 000 requests/hour)."
            )
        raise PermissionError(
            f"[bold red]Access denied when fetching {context}.[/bold red] "
            "If this is a private repo, make sure your GitHub token has the 'repo' scope."
        )
    if resp.status_code == 401:
        raise PermissionError(
            "[bold red]GitHub token is invalid or expired.[/bold red] "
            "Please update your token in the config file."
        )
    resp.raise_for_status()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_readme(owner: str, repo: str, token: str | None = None) -> str:
    """Fetch the raw README markdown for *owner*/*repo*.

    Returns:
        The README content as a string.

    Raises:
        FileNotFoundError: Repository or README doesn't exist.
        PermissionError:   Rate-limited or insufficient permissions.
        ConnectionError:   Network issue reaching the GitHub API.
    """
    url = f"{_API_BASE}/repos/{owner}/{repo}/readme"
    try:
        resp = requests.get(url, headers=_build_headers(token, raw=True), timeout=15)
    except requests.ConnectionError as exc:
        raise ConnectionError(
            "[bold red]Could not reach the GitHub API.[/bold red] Check your internet connection."
        ) from exc
    except requests.Timeout as exc:
        raise ConnectionError(
            "[bold red]GitHub API request timed out.[/bold red] Try again in a moment."
        ) from exc

    _handle_response_errors(resp, context=f"README for {owner}/{repo}")
    return resp.text


def fetch_repo_info(owner: str, repo: str, token: str | None = None) -> RepoInfo:
    """Fetch repository metadata **and** README in two API calls.

    Returns:
        A :class:`RepoInfo` dataclass with all fields populated.

    Raises:
        FileNotFoundError: Repository doesn't exist.
        PermissionError:   Rate-limited or insufficient permissions.
        ConnectionError:   Network issue reaching the GitHub API.
    """
    # --- repo metadata -------------------------------------------------------
    meta_url = f"{_API_BASE}/repos/{owner}/{repo}"
    try:
        meta_resp = requests.get(meta_url, headers=_build_headers(token), timeout=15)
    except requests.ConnectionError as exc:
        raise ConnectionError(
            "[bold red]Could not reach the GitHub API.[/bold red] Check your internet connection."
        ) from exc
    except requests.Timeout as exc:
        raise ConnectionError(
            "[bold red]GitHub API request timed out.[/bold red] Try again in a moment."
        ) from exc

    _handle_response_errors(meta_resp, context=f"Repository {owner}/{repo}")
    meta: dict = meta_resp.json()

    # --- README (best-effort; missing README is non-fatal) -------------------
    try:
        readme = fetch_readme(owner, repo, token=token)
    except FileNotFoundError:
        readme = ""

    return RepoInfo(
        owner=owner,
        name=meta.get("name", repo),
        description=meta.get("description") or "",
        stars=meta.get("stargazers_count", 0),
        language=meta.get("language") or "",
        topics=meta.get("topics") or [],
        readme_content=readme,
        url=meta.get("html_url", f"https://github.com/{owner}/{repo}"),
    )
