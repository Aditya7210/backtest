"""Auth routes: Zerodha auth status, login URL, and access-token generation."""
from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import settings

router = APIRouter(tags=["auth"])


class TokenUpdate(BaseModel):
    access_token: str
    token_date: str = ""


class TokenGenerateRequest(BaseModel):
    request_token: str


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve_env_path() -> Path:
    configured = (settings.ENV_FILE_PATH or ".env").strip()
    candidate = Path(configured)
    if not candidate.is_absolute():
        candidate = _project_root() / candidate
    return candidate


def _today_ist_str() -> str:
    return datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()


def _token_is_current_day(token_date: str) -> bool:
    cleaned = (token_date or "").strip()
    if not cleaned:
        return False
    return cleaned == _today_ist_str()


def _extract_request_token(raw_value: str) -> str:
    cleaned = (raw_value or "").strip()
    if not cleaned:
        return ""

    if "request_token=" in cleaned:
        parsed = urlparse(cleaned)
        query_values = parse_qs(parsed.query)
        request_tokens = query_values.get("request_token") or []
        if request_tokens:
            return (request_tokens[0] or "").strip()

    if cleaned.startswith("request_token="):
        token = cleaned.split("=", 1)[1]
        if "&" in token:
            token = token.split("&", 1)[0]
        return token.strip()

    if "&" in cleaned and "=" in cleaned:
        query_values = parse_qs(cleaned)
        request_tokens = query_values.get("request_token") or []
        if request_tokens:
            return (request_tokens[0] or "").strip()

    return cleaned


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


def _persist_token_to_env(access_token: str, token_date: str) -> Path:
    env_path = _resolve_env_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str]
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    else:
        lines = []

    lines = _upsert_env_line(lines, "ZERODHA_ACCESS_TOKEN", access_token)
    lines = _upsert_env_line(lines, "ZERODHA_TOKEN_DATE", token_date)
    content = "\n".join(lines)
    if content and not content.endswith("\n"):
        content += "\n"

    temp_path = env_path.with_suffix(env_path.suffix + ".tmp")
    try:
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(env_path)
    except Exception:
        # Docker bind-mounted single files may reject atomic replace on mount points.
        # Fallback to direct write to preserve persistence.
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
        env_path.write_text(content, encoding="utf-8")

    os.environ["ZERODHA_ACCESS_TOKEN"] = access_token
    os.environ["ZERODHA_TOKEN_DATE"] = token_date
    settings.ZERODHA_ACCESS_TOKEN = access_token
    settings.ZERODHA_TOKEN_DATE = token_date
    return env_path


def _kite_client(api_key: str):
    try:
        from kiteconnect import KiteConnect
    except Exception as exc:  # pragma: no cover - defensive dependency guard
        raise HTTPException(
            status_code=500,
            detail="kiteconnect dependency missing in backend environment.",
        ) from exc
    return KiteConnect(api_key=api_key)


def _normalize_generation_error(exc: Exception) -> str:
    text = str(exc).lower()
    if "token" in text and ("expired" in text or "invalid" in text or "incorrect" in text):
        return "Unable to generate access token. Please login again."
    return "Unable to generate access token. Please login again."


@router.get("/auth/status")
async def auth_status():
    """Check if Zerodha credentials are configured and fresh for today."""
    api_key_set = bool((settings.ZERODHA_API_KEY or "").strip())
    api_secret_set = bool((settings.ZERODHA_API_SECRET or "").strip())
    access_token_set = bool((settings.ZERODHA_ACCESS_TOKEN or "").strip())
    token_date = (settings.ZERODHA_TOKEN_DATE or "").strip()
    token_is_current_day = _token_is_current_day(token_date)
    auth_ready = bool(api_key_set and api_secret_set and access_token_set and token_is_current_day)

    return {
        "api_key_set": api_key_set,
        "api_secret_set": api_secret_set,
        "access_token_set": access_token_set,
        "token_date": token_date,
        "token_is_current_day": token_is_current_day,
        "auth_ready": auth_ready,
    }


@router.get("/auth/login-url")
async def auth_login_url():
    """Generate Zerodha login URL for request_token issuance."""
    api_key = (settings.ZERODHA_API_KEY or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="ZERODHA_API_KEY is missing in environment.")

    kite = _kite_client(api_key)
    try:
        login_url = str(kite.login_url())
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unable to generate Zerodha login URL.") from exc

    return {"login_url": login_url}


@router.post("/auth/generate-token")
async def generate_token(body: TokenGenerateRequest):
    """Exchange request_token for access_token and persist it to .env."""
    api_key = (settings.ZERODHA_API_KEY or "").strip()
    api_secret = (settings.ZERODHA_API_SECRET or "").strip()

    if not api_key:
        raise HTTPException(status_code=400, detail="ZERODHA_API_KEY is missing in environment.")
    if not api_secret:
        raise HTTPException(status_code=400, detail="ZERODHA_API_SECRET is missing in environment.")

    request_token = _extract_request_token(body.request_token)
    if not request_token:
        raise HTTPException(status_code=422, detail="request_token is required.")

    kite = _kite_client(api_key)
    try:
        session_data: dict[str, Any] = kite.generate_session(request_token, api_secret=api_secret)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=_normalize_generation_error(exc)) from exc

    access_token = str(session_data.get("access_token") or "").strip()
    if not access_token:
        raise HTTPException(status_code=500, detail="Access token missing in Zerodha session response.")

    token_date = _today_ist_str()
    try:
        _persist_token_to_env(access_token, token_date)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Failed to persist token to .env. Check write permission and env path.",
        ) from exc

    return {"status": "connected", "token_date": token_date}


@router.post("/auth/token")
async def update_token(body: TokenUpdate):
    """Manual token update with persistence to .env (without request_token flow)."""
    cleaned_token = (body.access_token or "").strip()
    if not cleaned_token:
        raise HTTPException(status_code=422, detail="access_token is required.")

    token_date = (body.token_date or "").strip() or _today_ist_str()
    try:
        _persist_token_to_env(cleaned_token, token_date)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Failed to persist token to .env. Check write permission and env path.",
        ) from exc
    return {"status": "updated", "token_date": token_date}
