"""Reddit OAuth2 authentication with token caching and PRAW integration."""

from __future__ import annotations

import json
import logging
import secrets
import threading
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs

import praw
import requests

logger = logging.getLogger(__name__)

TOKEN_DIR = Path.home() / ".repoherald"
TOKEN_FILE = TOKEN_DIR / "tokens.json"
AUTHORIZE_URL = "https://www.reddit.com/api/v1/authorize"
TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
SCOPES = "submit identity"
CALLBACK_TIMEOUT = 120  # seconds

SUCCESS_HTML = """\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>RepoHerald</title></head>
<body style="display:flex;justify-content:center;align-items:center;height:100vh;
font-family:system-ui,sans-serif;background:#1a1a2e;color:#e0e0e0;margin:0">
<div style="text-align:center">
<p style="font-size:3rem;margin:0">&#x2705;</p>
<h1>RepoHerald authorized!</h1>
<p>You can close this tab.</p>
</div></body></html>"""

ERROR_HTML = """\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>RepoHerald</title></head>
<body style="display:flex;justify-content:center;align-items:center;height:100vh;
font-family:system-ui,sans-serif;background:#1a1a2e;color:#e0e0e0;margin:0">
<div style="text-align:center">
<p style="font-size:3rem;margin:0">&#x274C;</p>
<h1>Authorization failed</h1>
<p>{message}</p>
</div></body></html>"""


# ---------------------------------------------------------------------------
# Token persistence
# ---------------------------------------------------------------------------

def _load_tokens() -> dict | None:
    """Load cached tokens from disk, or return None."""
    if not TOKEN_FILE.exists():
        return None
    try:
        data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        if "access_token" in data and "refresh_token" in data and "expires_at" in data:
            return data
    except (json.JSONDecodeError, KeyError):
        logger.warning("Corrupt token file – will re-authenticate.")
    return None


def _save_tokens(tokens: dict) -> None:
    """Persist tokens to ~/.repoherald/tokens.json."""
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
    logger.debug("Tokens saved to %s", TOKEN_FILE)


def _is_token_expired(tokens: dict, margin: float = 60.0) -> bool:
    """Return True if the access token is expired (with a safety margin)."""
    return time.time() >= tokens["expires_at"] - margin


# ---------------------------------------------------------------------------
# Token exchange / refresh via requests (not PRAW) so we stay in control
# ---------------------------------------------------------------------------

def _exchange_code(
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    user_agent: str,
) -> dict:
    """Exchange an authorization code for access + refresh tokens."""
    resp = requests.post(
        TOKEN_URL,
        auth=(client_id, client_secret),
        headers={"User-Agent": user_agent},
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    if "error" in payload:
        raise RuntimeError(f"Reddit token error: {payload['error']}")
    return {
        "access_token": payload["access_token"],
        "refresh_token": payload["refresh_token"],
        "expires_at": time.time() + payload["expires_in"],
    }


def _refresh_access_token(
    refresh_token: str,
    client_id: str,
    client_secret: str,
    user_agent: str,
) -> dict:
    """Use a refresh token to obtain a new access token."""
    resp = requests.post(
        TOKEN_URL,
        auth=(client_id, client_secret),
        headers={"User-Agent": user_agent},
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    if "error" in payload:
        raise RuntimeError(f"Reddit refresh error: {payload['error']}")
    return {
        "access_token": payload["access_token"],
        "refresh_token": refresh_token,  # Reddit doesn't rotate refresh tokens
        "expires_at": time.time() + payload["expires_in"],
    }


# ---------------------------------------------------------------------------
# Local callback server
# ---------------------------------------------------------------------------

class _CallbackHandler(BaseHTTPRequestHandler):
    """Handles the single OAuth redirect callback from Reddit."""

    auth_code: str | None = None
    auth_error: str | None = None

    def do_GET(self) -> None:  # noqa: N802
        params = parse_qs(urlparse(self.path).query)

        if "error" in params:
            _CallbackHandler.auth_error = params["error"][0]
            message = "Access denied." if _CallbackHandler.auth_error == "access_denied" else (
                f"Error: {_CallbackHandler.auth_error}"
            )
            self._respond(403, ERROR_HTML.format(message=message))
        elif "code" in params:
            _CallbackHandler.auth_code = params["code"][0]
            self._respond(200, SUCCESS_HTML)
        else:
            self._respond(400, ERROR_HTML.format(message="Missing code parameter."))

        # Signal the server to shut down (from a background thread to avoid deadlock)
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def _respond(self, status: int, html: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        logger.debug(format, *args)


def _run_callback_server(port: int) -> str:
    """Start a one-shot HTTP server, wait for the callback, return the auth code."""
    # Reset class-level state
    _CallbackHandler.auth_code = None
    _CallbackHandler.auth_error = None

    server = HTTPServer(("127.0.0.1", port), _CallbackHandler)
    server.timeout = CALLBACK_TIMEOUT

    # Use serve_forever with a poll interval so shutdown() works reliably
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    server_thread.join(timeout=CALLBACK_TIMEOUT)

    server.shutdown()
    server.server_close()

    if _CallbackHandler.auth_error:
        raise PermissionError(
            f"Reddit authorization denied: {_CallbackHandler.auth_error}"
        )
    if _CallbackHandler.auth_code is None:
        raise TimeoutError(
            f"No callback received within {CALLBACK_TIMEOUT} seconds. "
            "Please try again."
        )
    return _CallbackHandler.auth_code


# ---------------------------------------------------------------------------
# Full OAuth flow
# ---------------------------------------------------------------------------

def run_oauth_flow(
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    user_agent: str,
) -> dict:
    """Run the full OAuth2 authorization-code flow and return token dict."""
    state = secrets.token_urlsafe(32)

    parsed = urlparse(redirect_uri)
    port = parsed.port or 8080

    auth_params = urlencode({
        "client_id": client_id,
        "response_type": "code",
        "state": state,
        "redirect_uri": redirect_uri,
        "duration": "permanent",
        "scope": SCOPES,
    })
    auth_url = f"{AUTHORIZE_URL}?{auth_params}"

    logger.info("Opening browser for Reddit authorization…")
    webbrowser.open(auth_url)

    code = _run_callback_server(port)

    tokens = _exchange_code(code, client_id, client_secret, redirect_uri, user_agent)
    _save_tokens(tokens)
    logger.info("Authentication successful – tokens cached.")
    return tokens


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_reddit_instance(reddit_config: dict) -> praw.Reddit:
    """Return an authenticated praw.Reddit instance.

    *reddit_config* must contain: client_id, client_secret, redirect_uri,
    user_agent.

    Cached tokens are reused when possible; expired tokens are refreshed
    automatically.  If no cached tokens exist the full browser-based OAuth
    flow is triggered.
    """
    client_id: str = reddit_config["client_id"]
    client_secret: str = reddit_config["client_secret"]
    redirect_uri: str = reddit_config["redirect_uri"]
    user_agent: str = reddit_config["user_agent"]

    tokens = _load_tokens()

    if tokens is not None:
        if _is_token_expired(tokens):
            logger.info("Access token expired – refreshing…")
            try:
                tokens = _refresh_access_token(
                    tokens["refresh_token"], client_id, client_secret, user_agent,
                )
                _save_tokens(tokens)
            except (requests.RequestException, RuntimeError):
                logger.warning("Token refresh failed – re-authenticating.")
                tokens = None

    if tokens is None:
        tokens = run_oauth_flow(client_id, client_secret, redirect_uri, user_agent)

    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=tokens["refresh_token"],
        user_agent=user_agent,
    )
