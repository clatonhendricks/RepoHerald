"""Pydantic data models for RepoHerald."""

from __future__ import annotations

from pydantic import BaseModel


class SubredditSuggestion(BaseModel):
    """A suggested subreddit from the LLM."""

    name: str
    reason: str
    custom_title: str | None = None
    custom_body: str | None = None


class PostDraft(BaseModel):
    """The generated post content."""

    title: str
    body: str
    subreddits: list[SubredditSuggestion]
    repo_url: str
    repo_name: str


class PostResult(BaseModel):
    """Result of posting to a single subreddit."""

    subreddit: str
    success: bool
    url: str | None = None
    error: str | None = None


class LLMResponse(BaseModel):
    """Raw structured response from the LLM."""

    title: str
    body: str
    subreddits: list[SubredditSuggestion]
