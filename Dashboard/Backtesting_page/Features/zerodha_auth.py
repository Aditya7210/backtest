from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from kiteconnect import KiteConnect


def load_env_variables(env_path: str) -> dict[str, str | None]:
    """
    Load Zerodha credentials from a .env file without auto-loading environment variables.
    """

    path = Path(env_path)
    if not path.is_file():
        raise ValueError(f".env file not found: {path}")

    variables = _parse_env_file(path)

    api_key = (variables.get("ZERODHA_API_KEY") or "").strip()
    api_secret = (variables.get("ZERODHA_API_SECRET") or "").strip()
    access_token = variables.get("ZERODHA_ACCESS_TOKEN")
    access_token = access_token.strip() if isinstance(access_token, str) else None

    if not api_key:
        raise ValueError("Missing required variable: ZERODHA_API_KEY")
    if not api_secret:
        raise ValueError("Missing required variable: ZERODHA_API_SECRET")

    return {
        "api_key": api_key,
        "api_secret": api_secret,
        "access_token": access_token or None,
    }


def get_login_url(api_key: str) -> str:
    """Generate Zerodha login URL for request token generation."""

    kite = KiteConnect(api_key=api_key)
    return str(kite.login_url())


def generate_access_token(api_key: str, api_secret: str, request_token: str) -> str:
    """Exchange request_token for access_token using Zerodha generate_session API."""

    cleaned_request_token = (request_token or "").strip()
    if not cleaned_request_token:
        raise RuntimeError("Invalid request token")

    kite = KiteConnect(api_key=api_key)
    try:
        data: dict[str, Any] = kite.generate_session(
            cleaned_request_token,
            api_secret=api_secret,
        )
    except Exception as exc:
        raise RuntimeError("Unable to generate access token from request token") from exc

    access_token = data.get("access_token")
    if not access_token:
        raise RuntimeError("Access token missing in Zerodha session response")

    return str(access_token)


def save_access_token_to_env(env_path: str, access_token: str) -> None:
    """
    Update or append ZERODHA_ACCESS_TOKEN (and ZERODHA_TOKEN_DATE) in the .env file.
    """

    cleaned_token = (access_token or "").strip()
    if not cleaned_token:
        raise ValueError("access_token cannot be empty")

    path = Path(env_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str]
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    else:
        lines = []

    today_str = date.today().isoformat()

    lines = _upsert_env_line(lines, "ZERODHA_ACCESS_TOKEN", cleaned_token)
    lines = _upsert_env_line(lines, "ZERODHA_TOKEN_DATE", today_str)

    content = "\n".join(lines)
    if content and not content.endswith("\n"):
        content += "\n"

    temp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(path)
    except Exception as exc:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
        raise RuntimeError(f"Failed to persist access token to .env: {path}") from exc


def is_token_expired(token_date: str) -> bool:
    """
    Zerodha access tokens are generally valid for the day; compare token date with today.
    """

    cleaned = (token_date or "").strip()
    if not cleaned:
        return True

    try:
        token_dt = date.fromisoformat(cleaned)
    except ValueError as exc:
        raise ValueError("token_date must be in YYYY-MM-DD format") from exc

    return token_dt < date.today()


def _parse_env_file(path: Path) -> dict[str, str]:
    variables: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = raw_line.split("=", 1)
        key = key.strip()
        if not key or key.startswith("#"):
            continue

        parsed_value = value.strip()
        if len(parsed_value) >= 2 and (
            (parsed_value[0] == '"' and parsed_value[-1] == '"')
            or (parsed_value[0] == "'" and parsed_value[-1] == "'")
        ):
            parsed_value = parsed_value[1:-1]

        variables[key] = parsed_value

    return variables


def _upsert_env_line(lines: list[str], key: str, value: str) -> list[str]:
    updated = False
    output_lines: list[str] = []

    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("#") or "=" not in line:
            output_lines.append(line)
            continue

        existing_key = line.split("=", 1)[0].strip()
        if existing_key == key:
            output_lines.append(f"{key}={value}")
            updated = True
        else:
            output_lines.append(line)

    if not updated:
        output_lines.append(f"{key}={value}")

    return output_lines


__all__ = [
    "generate_access_token",
    "get_login_url",
    "is_token_expired",
    "load_env_variables",
    "save_access_token_to_env",
]
