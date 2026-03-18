<div align="center">

# 📣 RepoHerald

**Promote your GitHub repos on Reddit — AI-powered announcements**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()

</div>

---

RepoHerald is a cross-platform Python CLI tool that automates promoting GitHub repositories on Reddit. Give it a GitHub repo URL, and it uses LLMs to generate an announcement post, suggest relevant subreddits, and post to all approved communities after your review.

## ✨ Features

- 🤖 **AI-powered** — Supports OpenAI, Claude, Gemini, and Ollama (local models)
- 📋 **Smart subreddit suggestions** — LLM analyzes your project to find the right communities
- ✏️ **Interactive editing** — Review and customize everything before posting
- 🔧 **Per-subreddit customization** — Tailor titles and bodies for different communities
- 🔒 **Secure** — OAuth2 browser-based flow with token caching (no passwords stored)
- 🧪 **Dry-run mode** — Preview the full workflow without actually posting
- 🎨 **Beautiful terminal UI** — Powered by [Rich](https://github.com/Textualize/rich)
- 💻 **Cross-platform** — Windows, macOS, and Linux

## 🚀 Quick Start

```bash
pip install -e .
repoherald https://github.com/user/awesome-tool
```

## 📦 Installation

**Requirements:** Python 3.10 or newer.

### From Source

```bash
git clone https://github.com/your-username/repoherald.git
cd repoherald
pip install -e .
```

Verify the installation:

```bash
repoherald --help
```

## ⚙️ Configuration

RepoHerald stores its configuration at:

```
~/.repoherald/config.yaml
```

On first run, the example config is automatically copied there. You can also create it manually by copying `config.example.yaml` from the repo root.

### Full Config Reference

```yaml
# RepoHerald Configuration
# ~/.repoherald/config.yaml

# ─── LLM Provider Settings ───────────────────────────────────────────────────
llm:
  # Which provider to use: openai | claude | gemini | ollama
  provider: openai

  openai:
    api_key: "your-openai-api-key"
    model: "gpt-4o"                    # Any OpenAI chat model

  claude:
    api_key: "your-anthropic-api-key"
    model: "claude-sonnet-4-20250514"          # Any Anthropic model

  gemini:
    api_key: "your-google-ai-api-key"
    model: "gemini-2.0-flash"          # Any Google Generative AI model

  ollama:
    host: "http://localhost:11434"     # Ollama server address
    model: "llama3.2"                  # Any model you've pulled locally

# ─── Reddit Settings ─────────────────────────────────────────────────────────
reddit:
  client_id: "your-reddit-client-id"
  client_secret: "your-reddit-client-secret"
  redirect_uri: "http://localhost:8080"
  user_agent: "RepoHerald/0.1.0"

# ─── GitHub Settings (Optional) ──────────────────────────────────────────────
# A token is only needed for private repos or to avoid rate limits
# (60 requests/hour without a token, 5,000 with one).
github:
  token: ""  # Personal access token

# ─── Posting Settings ────────────────────────────────────────────────────────
posting:
  delay_between_posts: 10  # Seconds between posts (respects Reddit rate limits)
  post_type: "self"        # "self" for text posts, "link" for link posts
```

## 🔑 Reddit App Setup

You need a Reddit application to authenticate. Follow these steps:

1. Go to **<https://www.reddit.com/prefs/apps>** (log in if prompted).
2. Scroll down and click **"create another app..."**.
3. Fill in the form:
   - **Name:** `RepoHerald` (or any name you like)
   - **App type:** Select **"web app"**
   - **Description:** (optional)
   - **About URL:** (optional)
   - **Redirect URI:** `http://localhost:8080`
4. Click **"create app"**.
5. Copy the credentials:
   - **Client ID** — the string shown directly under the app name
   - **Client Secret** — labeled "secret"
6. Add both to your config file:

   ```yaml
   reddit:
     client_id: "paste-client-id-here"
     client_secret: "paste-secret-here"
   ```

On first use, RepoHerald will open your browser to authorize the app. Tokens are cached at `~/.repoherald/tokens.json` and refreshed automatically — you only need to log in once.

## 🧠 LLM Provider Setup

Configure at least one LLM provider. Set `llm.provider` in your config to the one you want to use.

### OpenAI

1. Get an API key at <https://platform.openai.com/api-keys>.
2. Add it to your config:
   ```yaml
   llm:
     provider: openai
     openai:
       api_key: "sk-..."
       model: "gpt-4o"
   ```

### Claude (Anthropic)

1. Get an API key at <https://console.anthropic.com/>.
2. Add it to your config:
   ```yaml
   llm:
     provider: claude
     claude:
       api_key: "sk-ant-..."
       model: "claude-sonnet-4-20250514"
   ```

### Gemini (Google)

1. Get an API key at <https://aistudio.google.com/app/apikey>.
2. Add it to your config:
   ```yaml
   llm:
     provider: gemini
     gemini:
       api_key: "AI..."
       model: "gemini-2.0-flash"
   ```

### Ollama (Local)

No API key needed — runs entirely on your machine.

1. Install Ollama from <https://ollama.ai>.
2. Pull a model:
   ```bash
   ollama pull llama3.2
   ```
3. Set your config:
   ```yaml
   llm:
     provider: ollama
     ollama:
       host: "http://localhost:11434"
       model: "llama3.2"
   ```

## 📖 Usage

### Basic

```bash
repoherald https://github.com/user/repo
```

### Dry-Run Mode

Preview everything without actually posting to Reddit:

```bash
repoherald https://github.com/user/repo --dry-run
```

### Custom Config File

```bash
repoherald https://github.com/user/repo --config ./my-config.yaml
```

### Override LLM Provider

```bash
repoherald https://github.com/user/repo --provider claude
```

## 🔄 How It Works

```
GitHub Repo URL
      │
      ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Fetch      │     │  Generate   │     │  Interactive │
│   README &   │────▶│  Post via   │────▶│  Review &   │
│   Metadata   │     │  LLM        │     │  Edit       │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
                                               ▼
                                        ┌─────────────┐
                                        │  Post to    │
                                        │  Reddit     │
                                        └─────────────┘
```

1. **Fetch** — Retrieves the README and repository metadata (description, stars, language, topics) from the GitHub API.
2. **Generate** — Sends the project context to your chosen LLM, which crafts a Reddit announcement title, body, and a list of suggested subreddits with reasons.
3. **Review** — Presents everything in a rich terminal UI. You can edit the title, body, and subreddit list, or customize content per subreddit.
4. **Approve** — You confirm which subreddits to post to.
5. **Post** — Submits to each selected subreddit with configurable delays between posts to respect Reddit's rate limits.

## 🛠️ Development

Install with development dependencies:

```bash
pip install -e ".[dev]"
```

### Linting

```bash
ruff check .
```

### Testing

```bash
pytest
```

### Project Structure

```
repoherald/
├── __init__.py          # Package version
├── __main__.py          # python -m repoherald entry point
├── cli.py               # Click CLI commands
├── config.py            # YAML config loading & validation (Pydantic)
├── github_fetcher.py    # GitHub API client (repo metadata + README)
├── models.py            # Data models (PostDraft, PostResult, etc.)
├── llm/
│   ├── __init__.py      # Provider factory
│   ├── base.py          # Abstract LLM interface & prompt templates
│   ├── openai_provider.py
│   ├── claude_provider.py
│   ├── gemini_provider.py
│   └── ollama_provider.py
└── reddit/
    ├── __init__.py
    ├── auth.py          # OAuth2 flow with token caching
    └── poster.py        # Subreddit posting & rate limiting
```

## 📄 License

This project is licensed under the [MIT License](LICENSE).
