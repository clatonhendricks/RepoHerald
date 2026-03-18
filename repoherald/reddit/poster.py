"""Reddit posting helpers for RepoHerald."""

from __future__ import annotations

import logging
import time
from typing import Callable

import praw
import praw.exceptions

from repoherald.models import PostDraft, PostResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Single-subreddit post
# ---------------------------------------------------------------------------

def post_to_subreddit(
    reddit: praw.Reddit,
    subreddit_name: str,
    title: str,
    body: str,
    post_type: str = "self",
) -> PostResult:
    """Submit a post to a single subreddit and return a PostResult."""
    name = subreddit_name.lstrip("r/") if subreddit_name.startswith("r/") else subreddit_name

    try:
        subreddit = reddit.subreddit(name)

        if post_type == "link":
            submission = subreddit.submit(title, url=body)
        else:
            submission = subreddit.submit(title, selftext=body)

        logger.info("Posted to r/%s: %s", name, submission.url)
        return PostResult(subreddit=name, success=True, url=submission.url)

    except praw.exceptions.RedditAPIException as exc:
        logger.error("Reddit API error for r/%s: %s", name, exc)
        return PostResult(subreddit=name, success=False, error=str(exc))
    except (
        praw.exceptions.PRAWException,
        Exception,
    ) as exc:
        # Covers Forbidden, NotFound, APIException, and other PRAW errors
        # that surface as prawcore exceptions (e.g. prawcore.Forbidden).
        logger.error("Error posting to r/%s: %s", name, exc)
        return PostResult(subreddit=name, success=False, error=str(exc))


# ---------------------------------------------------------------------------
# Batch post to all subreddits in a draft
# ---------------------------------------------------------------------------

def post_to_all(
    reddit: praw.Reddit,
    draft: PostDraft,
    post_type: str = "self",
    delay: int = 10,
    dry_run: bool = False,
    callback: Callable[[PostResult, int, int], None] | None = None,
) -> list[PostResult]:
    """Post to every subreddit listed in *draft* and return results.

    Parameters
    ----------
    reddit:
        Authenticated PRAW instance.
    draft:
        The post content and target subreddits.
    post_type:
        ``"self"`` for text posts, ``"link"`` for link posts.
    delay:
        Seconds to wait between posts (rate-limit courtesy).
    dry_run:
        If ``True``, skip actual posting and return placeholder results.
    callback:
        Optional ``(result, index, total)`` callable invoked after each post.
    """
    results: list[PostResult] = []
    total = len(draft.subreddits)

    for idx, sub in enumerate(draft.subreddits):
        title = sub.custom_title or draft.title
        body = sub.custom_body or draft.body

        if dry_run:
            result = PostResult(
                subreddit=sub.name,
                success=True,
                url="[DRY RUN]",
            )
            logger.info("[DRY RUN] Would post to r/%s", sub.name)
        else:
            result = post_to_subreddit(reddit, sub.name, title, body, post_type)

        results.append(result)

        if callback is not None:
            callback(result, idx, total)

        # Rate-limit pause between posts (skip after the last one)
        if idx < total - 1:
            time.sleep(delay)

    return results


# ---------------------------------------------------------------------------
# Subreddit validation
# ---------------------------------------------------------------------------

def validate_subreddits(
    reddit: praw.Reddit,
    subreddit_names: list[str],
) -> dict[str, bool]:
    """Check whether each subreddit exists and is accessible.

    Returns a mapping of subreddit name → ``True`` (accessible) or ``False``.
    """
    results: dict[str, bool] = {}

    for name in subreddit_names:
        name = name.lstrip("r/") if name.startswith("r/") else name
        try:
            # Accessing .id forces a fetch; raises if the sub is
            # private, banned, or nonexistent.
            _ = reddit.subreddit(name).id
            results[name] = True
        except Exception:
            logger.debug("Subreddit r/%s is not accessible.", name)
            results[name] = False

    return results
