"""CLI entry point for RepoHerald — ties all modules together."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table

from repoherald.config import AppConfig, LLMProvider as LLMProviderEnum, get_active_llm_config, load_config, validate_reddit_config
from repoherald.github_fetcher import RepoInfo, fetch_repo_info, parse_github_url
from repoherald.llm import create_provider
from repoherald.models import PostDraft, PostResult, SubredditSuggestion
from repoherald.reddit.auth import get_reddit_instance
from repoherald.reddit.poster import post_to_all

console = Console()

# ── Display helpers ──────────────────────────────────────────────────────────


def display_repo_info(repo: RepoInfo) -> None:
    """Show a summary panel for the fetched repository."""
    topics = ", ".join(repo.topics) if repo.topics else "—"
    body = (
        f"[bold]{repo.owner}/{repo.name}[/bold]\n"
        f"[dim]{repo.description or '(no description)'}[/dim]\n\n"
        f"⭐ [yellow]{repo.stars:,}[/yellow]  "
        f"🗂  [cyan]{repo.language or 'N/A'}[/cyan]  "
        f"🏷  {topics}"
    )
    console.print(Panel(body, title="📦 Repository Info", border_style="cyan"))


def display_draft(draft: PostDraft) -> None:
    """Render the full draft — title, body, and subreddits."""
    console.print()
    console.print(Panel(f"[bold]{draft.title}[/bold]", title="📝 Title", border_style="green"))
    console.print(Panel(Markdown(draft.body), title="📄 Body", border_style="green"))
    _display_subreddit_table(draft.subreddits)


def _display_subreddit_table(subreddits: list[SubredditSuggestion]) -> None:
    """Render the subreddit suggestion table."""
    table = Table(title="🎯 Target Subreddits", border_style="cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("Subreddit", style="bold cyan")
    table.add_column("Reason")
    table.add_column("Custom?", justify="center", width=8)
    for idx, sub in enumerate(subreddits, 1):
        custom = "✏️" if sub.custom_title or sub.custom_body else ""
        table.add_row(str(idx), sub.name, sub.reason, custom)
    console.print(table)


def display_results(results: list[PostResult], dry_run: bool) -> None:
    """Show a results table after posting."""
    table = Table(title="📊 Posting Results", border_style="green")
    table.add_column("Subreddit", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("URL / Error")

    for r in results:
        if r.success:
            table.add_row(f"r/{r.subreddit}", "[bold green]✅[/bold green]", r.url or "")
        else:
            table.add_row(f"r/{r.subreddit}", "[bold red]❌[/bold red]", f"[red]{r.error}[/red]")

    console.print(table)

    successes = sum(1 for r in results if r.success)
    failures = len(results) - successes
    console.print(
        f"\n[green]{successes} succeeded[/green]"
        + (f", [red]{failures} failed[/red]" if failures else "")
    )

    if dry_run:
        console.print(
            Panel(
                "[bold yellow]DRY RUN — No posts were actually made.[/bold yellow]",
                border_style="yellow",
            )
        )


# ── LLM generation ──────────────────────────────────────────────────────────


def _provider_display_name(config: AppConfig) -> str:
    """Human-readable provider + model string for status messages."""
    info = get_active_llm_config(config)
    provider = info["provider"].capitalize()
    model = info.get("model") or info.get("host", "")
    return f"{provider} ({model})"


def generate_draft(config: AppConfig, repo: RepoInfo, provider_override: str | None = None) -> PostDraft:
    """Call the LLM and return a PostDraft."""
    if provider_override:
        config.llm.provider = LLMProviderEnum(provider_override)

    label = _provider_display_name(config)
    provider = create_provider(config)

    with console.status(f"[cyan]🤖 Generating announcement with {label}…[/cyan]"):
        result = provider.generate(
            readme_content=repo.readme_content,
            repo_name=f"{repo.owner}/{repo.name}",
            repo_url=repo.url,
            repo_description=repo.description,
            repo_language=repo.language,
            repo_stars=repo.stars,
        )

    subreddits = [
        SubredditSuggestion(name=s.get("name", ""), reason=s.get("reason", ""))
        for s in result.get("subreddits", [])
    ]
    return PostDraft(
        title=result["title"],
        body=result["body"],
        subreddits=subreddits,
        repo_url=repo.url,
        repo_name=f"{repo.owner}/{repo.name}",
    )


# ── Interactive review loop ─────────────────────────────────────────────────


def _edit_title(draft: PostDraft) -> PostDraft:
    console.print(f"\n[dim]Current title:[/dim] {draft.title}")
    new_title = Prompt.ask("[cyan]New title[/cyan]", default=draft.title)
    draft = draft.model_copy(update={"title": new_title})
    console.print(Panel(f"[bold]{draft.title}[/bold]", title="📝 Updated Title", border_style="green"))
    return draft


def _edit_body(draft: PostDraft) -> PostDraft:
    console.print("\n[dim]Opening editor for body… (save & close to apply)[/dim]")
    new_body = click.edit(draft.body)
    if new_body is not None:
        new_body = new_body.strip()
        if new_body:
            draft = draft.model_copy(update={"body": new_body})
            console.print(Panel(Markdown(draft.body), title="📄 Updated Body", border_style="green"))
        else:
            console.print("[yellow]Empty body — keeping original.[/yellow]")
    else:
        console.print("[yellow]Editor closed without changes.[/yellow]")
    return draft


def _edit_subreddits(draft: PostDraft) -> PostDraft:
    """Add/remove subreddits interactively."""
    subreddits = list(draft.subreddits)

    while True:
        console.print()
        _display_subreddit_table(subreddits)
        choice = Prompt.ask(
            "[cyan]\\[a][/cyan] Add  [cyan]\\[r][/cyan] Remove  [cyan]\\[b][/cyan] Back",
            choices=["a", "r", "b"],
            default="b",
        )

        if choice == "a":
            name = Prompt.ask("[cyan]Subreddit name (e.g. r/Python)[/cyan]")
            reason = Prompt.ask("[cyan]Reason[/cyan]", default="Manually added")
            subreddits.append(SubredditSuggestion(name=name, reason=reason))
            console.print(f"[green]Added {name}[/green]")

        elif choice == "r":
            if not subreddits:
                console.print("[yellow]No subreddits to remove.[/yellow]")
                continue
            num = Prompt.ask(
                "[cyan]Remove # (number)[/cyan]",
                default="0",
            )
            try:
                idx = int(num) - 1
                if 0 <= idx < len(subreddits):
                    removed = subreddits.pop(idx)
                    console.print(f"[red]Removed {removed.name}[/red]")
                else:
                    console.print("[yellow]Invalid number.[/yellow]")
            except ValueError:
                console.print("[yellow]Please enter a valid number.[/yellow]")

        else:
            break

    return draft.model_copy(update={"subreddits": subreddits})


def _customize_per_subreddit(draft: PostDraft) -> PostDraft:
    """Let the user set a custom title/body for a specific subreddit."""
    _display_subreddit_table(draft.subreddits)
    num = Prompt.ask("[cyan]Subreddit # to customize[/cyan]", default="0")
    try:
        idx = int(num) - 1
        if not (0 <= idx < len(draft.subreddits)):
            console.print("[yellow]Invalid number.[/yellow]")
            return draft
    except ValueError:
        console.print("[yellow]Please enter a valid number.[/yellow]")
        return draft

    sub = draft.subreddits[idx]
    console.print(f"\nCustomising [bold cyan]{sub.name}[/bold cyan]")

    new_title = Prompt.ask(
        "[cyan]Custom title[/cyan] (leave blank to use default)",
        default=sub.custom_title or "",
    )
    new_body_choice = Confirm.ask("[cyan]Edit body for this subreddit?[/cyan]", default=False)
    new_body: str | None = sub.custom_body
    if new_body_choice:
        edited = click.edit(sub.custom_body or draft.body)
        if edited is not None and edited.strip():
            new_body = edited.strip()

    updated_sub = sub.model_copy(
        update={
            "custom_title": new_title if new_title else None,
            "custom_body": new_body,
        }
    )
    subreddits = list(draft.subreddits)
    subreddits[idx] = updated_sub
    draft = draft.model_copy(update={"subreddits": subreddits})
    console.print(f"[green]Customised {sub.name}[/green]")
    return draft


MENU = """\
[bold]What would you like to do?[/bold]
[cyan]\\[1][/cyan] ✅ Approve and post
[cyan]\\[2][/cyan] ✏️  Edit title
[cyan]\\[3][/cyan] ✏️  Edit body
[cyan]\\[4][/cyan] 📋 Edit subreddits (add/remove)
[cyan]\\[5][/cyan] 🔧 Customize per subreddit
[cyan]\\[6][/cyan] 🔄 Regenerate with LLM
[cyan]\\[7][/cyan] ❌ Cancel"""


def review_loop(draft: PostDraft, config: AppConfig, repo: RepoInfo) -> PostDraft | None:
    """Interactive edit/approve loop.  Returns the final draft, or None to cancel."""
    while True:
        console.print(f"\n{MENU}")
        choice = Prompt.ask("[cyan]Choice[/cyan]", choices=["1", "2", "3", "4", "5", "6", "7"], default="1")

        if choice == "1":
            return draft
        elif choice == "2":
            draft = _edit_title(draft)
        elif choice == "3":
            draft = _edit_body(draft)
        elif choice == "4":
            draft = _edit_subreddits(draft)
        elif choice == "5":
            draft = _customize_per_subreddit(draft)
        elif choice == "6":
            try:
                draft = generate_draft(config, repo)
                display_draft(draft)
            except (ValueError, RuntimeError, ConnectionError) as exc:
                console.print(f"[bold red]Error:[/bold red] {exc}")
        elif choice == "7":
            console.print("[yellow]Cancelled.[/yellow]")
            return None


# ── Posting ──────────────────────────────────────────────────────────────────


def do_posting(config: AppConfig, draft: PostDraft, dry_run: bool) -> None:
    """Authenticate with Reddit and post (or dry-run)."""
    reddit = None
    if not dry_run:
        validate_reddit_config(config)
        with console.status("[cyan]🔑 Authenticating with Reddit…[/cyan]"):
            reddit_cfg = config.reddit.model_dump()
            reddit = get_reddit_instance(reddit_cfg)
        console.print("[green]Authenticated with Reddit ✓[/green]")

    total = len(draft.subreddits)
    results: list[PostResult] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Posting…", total=total)

        def _callback(result: PostResult, index: int, _total: int) -> None:
            status = "✅" if result.success else "❌"
            progress.update(task, advance=1, description=f"[cyan]{status} r/{result.subreddit}")
            results.append(result)

        if dry_run:
            post_results = post_to_all(
                reddit=None,  # type: ignore[arg-type]
                draft=draft,
                post_type=config.posting.post_type,
                delay=0,
                dry_run=True,
                callback=_callback,
            )
        else:
            post_results = post_to_all(
                reddit=reddit,
                draft=draft,
                post_type=config.posting.post_type,
                delay=config.posting.delay_between_posts,
                dry_run=False,
                callback=_callback,
            )

    # The callback already collected results; but post_to_all also returns them.
    display_results(post_results, dry_run)


# ── Main Click command ───────────────────────────────────────────────────────


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("github_url")
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to config YAML file (default: ~/.repoherald/config.yaml).",
)
@click.option("--dry-run", is_flag=True, default=False, help="Preview without posting to Reddit.")
@click.option(
    "--provider",
    "provider_override",
    type=click.Choice(["openai", "claude", "gemini", "ollama"], case_sensitive=False),
    default=None,
    help="Override the LLM provider from config.",
)
@click.version_option(package_name="repoherald")
def main(
    github_url: str,
    config_path: Path | None,
    dry_run: bool,
    provider_override: str | None,
) -> None:
    """🚀 RepoHerald — Promote your GitHub repos on Reddit.

    Provide a GITHUB_URL (e.g. https://github.com/user/repo) and RepoHerald
    will fetch the repo info, generate an announcement with an LLM, and let
    you review, edit, and post it to relevant subreddits.
    """
    # ── 1. Load config ──────────────────────────────────────────────────
    try:
        config = load_config(config_path)
    except click.ClickException:
        raise
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        sys.exit(1)

    if dry_run:
        console.print("[bold yellow]🏜  Dry-run mode — nothing will be posted.[/bold yellow]\n")

    # ── 2. Parse URL & fetch repo info ──────────────────────────────────
    try:
        owner, repo_name = parse_github_url(github_url)
    except ValueError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        sys.exit(1)

    try:
        with console.status(f"[cyan]⏳ Fetching repository info for {owner}/{repo_name}…[/cyan]"):
            token = config.github.token or None
            repo = fetch_repo_info(owner, repo_name, token=token)
    except (FileNotFoundError, PermissionError, ConnectionError) as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        sys.exit(1)

    display_repo_info(repo)

    # ── 3. Generate draft with LLM ──────────────────────────────────────
    try:
        draft = generate_draft(config, repo, provider_override)
    except (ValueError, RuntimeError, ConnectionError) as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        sys.exit(1)

    display_draft(draft)

    # ── 4. Interactive review loop ──────────────────────────────────────
    final_draft = review_loop(draft, config, repo)
    if final_draft is None:
        sys.exit(0)

    # ── 5. Post to Reddit ───────────────────────────────────────────────
    try:
        do_posting(config, final_draft, dry_run)
    except (PermissionError, TimeoutError, ConnectionError, RuntimeError) as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        sys.exit(1)

    console.print("\n[bold green]Done! 🎉[/bold green]")
