"""Who owns the GitHub token: that login is the approver (ADR-0016)."""

import httpx

from ichnos.settings import Settings

GITHUB_API = "https://api.github.com"


class IdentityError(Exception):
    """The token owner could not be identified; the message is safe to show."""


def token_login(settings: Settings, transport: httpx.BaseTransport | None = None) -> str:
    token = settings.github_token
    if token is None or not token.get_secret_value():
        raise IdentityError(
            "No GitHub token is configured; the approver is the token's owner (ADR-0016)."
        )
    headers = {
        "Authorization": f"Bearer {token.get_secret_value()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        with httpx.Client(headers=headers, timeout=15.0, transport=transport) as client:
            response = client.get(f"{GITHUB_API}/user")
    except httpx.HTTPError as exc:
        raise IdentityError("Could not reach GitHub to identify the approver.") from exc
    if response.status_code != 200:
        raise IdentityError(
            f"GitHub did not identify the token owner (HTTP {response.status_code})."
        )
    login = response.json().get("login")
    if not isinstance(login, str) or not login:
        raise IdentityError("GitHub returned no login for the token owner.")
    return login
