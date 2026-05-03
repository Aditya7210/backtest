"""Repository for instrument master data."""
from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from kiteconnect import KiteConnect

from backend.config import settings
from backend.database.connection import get_db

_MAPPER_REQUIRED = [
    "instrument_token",
    "tradingsymbol",
    "name",
    "exchange",
    "segment",
    "expiry",
    "strike",
    "instrument_type",
    "lot_size",
]

_INDEX_ALIAS_MAP: dict[str, list[str]] = {
    "NIFTY": ["NIFTY 50", "NIFTY BANK", "NIFTY NEXT 50", "NIFTY 100", "NIFTY 500"],
    "NIFTY50": ["NIFTY 50"],
    "BANKNIFTY": ["NIFTY BANK"],
    "NIFTYBANK": ["NIFTY BANK"],
    "FINNIFTY": ["NIFTY FIN SERVICE"],
    "MIDCPNIFTY": ["NIFTY MID SELECT"],
    "INDIAVIX": ["INDIA VIX"],
    "VIX": ["INDIA VIX"],
    "SENSEX": ["SENSEX"],
    "BANKEX": ["BANKEX"],
}

_INDEX_QUERY_KEYS = set(_INDEX_ALIAS_MAP.keys())
_ZERODHA_DEFAULT_HISTORY_START = date(2015, 2, 1)


def _project_root() -> Path:
    here = Path(__file__).resolve()
    return here.parents[3]


def _mapper_dir() -> Path:
    return _project_root() / "Data" / "instrument_mapper_data"


def _latest_csv_path() -> Path:
    return _mapper_dir() / "zerodha_instruments_latest.csv"


def _archive_csv_path() -> Path:
    return _mapper_dir() / "zerodha_instruments_archive.csv"


def _metadata_path() -> Path:
    return _mapper_dir() / "metadata.json"


def _to_token(value: Any) -> int | None:
    try:
        parsed = int(float(str(value)))
    except Exception:
        return None
    return parsed if parsed > 0 else None


def _normalize_row(row: dict[str, Any]) -> dict[str, Any] | None:
    token = _to_token(row.get("instrument_token"))
    if token is None:
        return None
    symbol = str(row.get("tradingsymbol", "")).strip().upper()
    if not symbol:
        return None
    return {
        "instrument_token": token,
        "tradingsymbol": symbol,
        "name": str(row.get("name", "")).strip(),
        "segment": str(row.get("segment", "")).strip().upper(),
        "exchange": str(row.get("exchange", "")).strip().upper(),
        "instrument_type": str(row.get("instrument_type", "")).strip().upper(),
        "expiry": str(row.get("expiry", "")).strip(),
        "strike": str(row.get("strike", "")).strip(),
        "lot_size": str(row.get("lot_size", "")).strip(),
    }


def _load_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            row = _normalize_row(raw)
            if row is not None:
                rows.append(row)
    return rows


def _missing_required_columns(path: Path) -> list[str]:
    if not path.exists():
        return list(_MAPPER_REQUIRED)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = set(reader.fieldnames or [])
    return [col for col in _MAPPER_REQUIRED if col not in headers]


def _merge_latest_archive(
    latest_rows: list[dict[str, Any]],
    archive_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Preserve old tokens while preferring latest rows for duplicate tokens."""
    merged: list[dict[str, Any]] = []
    seen_tokens: set[int] = set()
    for row in latest_rows + archive_rows:
        token = int(row["instrument_token"])
        if token in seen_tokens:
            continue
        seen_tokens.add(token)
        merged.append(row)
    return merged


def _normalize_query(value: str) -> str:
    return "".join(ch for ch in value.upper().strip() if ch.isalnum())


def _is_index_like_query(normalized_query: str) -> bool:
    if normalized_query in _INDEX_QUERY_KEYS:
        return True
    for key in _INDEX_QUERY_KEYS:
        if key and key in normalized_query:
            return True
    return normalized_query.startswith("NIFTY")


def _is_derivative_query(normalized_query: str) -> bool:
    if any(tag in normalized_query for tag in ("CE", "PE", "FUT")):
        return True
    return any(ch.isdigit() for ch in normalized_query) and len(normalized_query) >= 8


def _is_etf_like_query(normalized_query: str) -> bool:
    return "ETF" in normalized_query or normalized_query.endswith("BEES")


def _query_tokens(value: str) -> list[str]:
    return [token for token in value.upper().replace("-", " ").replace("_", " ").split() if token]


def _text_key(value: str) -> str:
    return "".join(ch for ch in value.upper() if ch.isalnum())


def _is_index_row(item: dict[str, Any]) -> bool:
    segment = str(item.get("segment", "")).upper()
    exchange = str(item.get("exchange", "")).upper()
    symbol = str(item.get("tradingsymbol", "")).upper()
    return segment == "INDICES" or (exchange == "NSE" and ("NIFTY" in symbol or "VIX" in symbol))


def _is_nse_eq(item: dict[str, Any]) -> bool:
    exchange = str(item.get("exchange", "")).upper()
    instrument_type = str(item.get("instrument_type", "")).upper()
    return exchange == "NSE" and instrument_type == "EQ"


def _is_etf_row(item: dict[str, Any]) -> bool:
    symbol = str(item.get("tradingsymbol", "")).upper()
    name = str(item.get("name", "")).upper()
    return "ETF" in symbol or "EXCHANGE TRADED FUND" in name


def _is_derivative_row(item: dict[str, Any]) -> bool:
    segment = str(item.get("segment", "")).upper()
    instrument_type = str(item.get("instrument_type", "")).upper()
    return segment.startswith("NFO") or instrument_type in {"CE", "PE", "FUT"}


def _parse_iso_date(value: str) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except Exception:
        return None


def _availability_window(item: dict[str, Any]) -> tuple[str, str]:
    today = date.today()
    expiry = _parse_iso_date(str(item.get("expiry", "")))
    max_date = min(expiry, today) if expiry else today
    if max_date < _ZERODHA_DEFAULT_HISTORY_START:
        max_date = _ZERODHA_DEFAULT_HISTORY_START

    instrument_type = str(item.get("instrument_type", "")).upper()
    derivative = _is_derivative_row(item)
    if derivative and expiry:
        if instrument_type == "FUT":
            min_date = max_date - timedelta(days=365)
        elif instrument_type in {"CE", "PE"}:
            min_date = max_date - timedelta(days=180)
        else:
            min_date = max_date - timedelta(days=270)
    else:
        min_date = _ZERODHA_DEFAULT_HISTORY_START

    if min_date < _ZERODHA_DEFAULT_HISTORY_START:
        min_date = _ZERODHA_DEFAULT_HISTORY_START
    if min_date > max_date:
        min_date = max_date
    return min_date.isoformat(), max_date.isoformat()


def _alias_targets_list(normalized_query: str) -> list[str]:
    return [target.upper() for target in _INDEX_ALIAS_MAP.get(normalized_query, [])]


def _search_rank(item: dict[str, Any], raw_query: str, normalized_query: str) -> tuple[int, int, int, int, int, str]:
    symbol = str(item.get("tradingsymbol", "")).upper()
    name = str(item.get("name", "")).upper()
    tokens = _query_tokens(raw_query)
    symbol_key = _text_key(symbol)
    name_key = _text_key(name)
    index_query = _is_index_like_query(normalized_query)
    derivative_query = _is_derivative_query(normalized_query)
    etf_query = _is_etf_like_query(normalized_query)
    alias_targets = _alias_targets_list(normalized_query)

    exact_symbol = symbol == raw_query.upper() or symbol_key == normalized_query
    alias_exact = symbol in alias_targets
    alias_order = alias_targets.index(symbol) if alias_exact else 999
    index_row = _is_index_row(item)
    nse_eq = _is_nse_eq(item)
    etf_row = _is_etf_row(item)
    derivative_row = _is_derivative_row(item)
    starts_symbol = symbol.startswith(raw_query.upper()) or symbol_key.startswith(normalized_query)
    starts_name = bool(name and (name.startswith(raw_query.upper()) or name_key.startswith(normalized_query)))
    token_prefix_symbol = bool(tokens) and any(symbol.startswith(token) for token in tokens)
    token_prefix_name = bool(tokens) and any(name.startswith(token) for token in tokens)
    contains_symbol = normalized_query in symbol_key
    contains_name = normalized_query in name_key

    # Match quality first (applies to every instrument search).
    if exact_symbol:
        match_tier = 0
    elif name_key == normalized_query and (not derivative_row or derivative_query):
        match_tier = 1
    elif alias_exact:
        match_tier = 2
    elif starts_symbol:
        match_tier = 3
    elif starts_name:
        match_tier = 4
    elif token_prefix_symbol:
        match_tier = 5
    elif token_prefix_name:
        match_tier = 6
    elif contains_symbol:
        match_tier = 7
    elif contains_name:
        match_tier = 8
    else:
        match_tier = 9

    # Then apply query-intent category priority (works beyond NIFTY too).
    if derivative_query:
        if derivative_row:
            category_tier = 0
        elif nse_eq:
            category_tier = 1
        elif etf_row:
            category_tier = 2
        elif index_row:
            category_tier = 3
        else:
            category_tier = 4
    elif index_query:
        if index_row:
            category_tier = 0
        elif nse_eq:
            category_tier = 1
        elif etf_row:
            category_tier = 2
        elif derivative_row:
            category_tier = 3
        else:
            category_tier = 4
    elif etf_query:
        if etf_row:
            category_tier = 0
        elif nse_eq:
            category_tier = 1
        elif index_row:
            category_tier = 2
        elif derivative_row:
            category_tier = 3
        else:
            category_tier = 4
    else:
        if nse_eq:
            category_tier = 0
        elif index_row:
            category_tier = 1
        elif etf_row:
            category_tier = 2
        elif derivative_row:
            category_tier = 3
        else:
            category_tier = 4

    # Final tier is a weighted blend; match quality dominates.
    tier = match_tier * 10 + category_tier

    # Keep a slight demotion for derivatives on broad non-derivative queries.
    if not derivative_query and derivative_row and not exact_symbol:
        tier += 10

    # Small boost for index aliases (NIFTY/BANKNIFTY/...).
    if exact_symbol:
        tier = 0
    elif alias_exact:
        tier = min(tier, 12)

    # Secondary sort: prefer NSE and shorter symbol labels when tiers match.
    exchange_bias = 0 if str(item.get("exchange", "")).upper() == "NSE" else 1
    symbol_len = len(symbol)
    return (tier, alias_order, exchange_bias, symbol_len, int(item.get("instrument_token", 0)), symbol)


def search_mapper_files(query: str, limit: int = 50) -> dict[str, Any]:
    q = query.strip()
    if len(q) < 2:
        return {"items": [], "source": "mapper_csv", "warning": "Type at least 2 characters to search."}

    mapper_dir = _mapper_dir()
    latest_path = _latest_csv_path()
    archive_path = _archive_csv_path()
    if not latest_path.exists() and not archive_path.exists():
        return {
            "items": [],
            "source": "mapper_csv",
            "warning": f"Instrument mapper files not found at {mapper_dir}",
        }

    latest_missing = _missing_required_columns(latest_path) if latest_path.exists() else []
    archive_missing = _missing_required_columns(archive_path) if archive_path.exists() else []
    if latest_missing or archive_missing:
        problems: list[str] = []
        if latest_missing:
            problems.append(f"latest missing columns: {', '.join(latest_missing)}")
        if archive_missing:
            problems.append(f"archive missing columns: {', '.join(archive_missing)}")
        return {
            "items": [],
            "source": "mapper_csv",
            "warning": "; ".join(problems),
        }

    needle = q.upper()
    normalized_query = _normalize_query(q)
    alias_targets = set(_alias_targets_list(normalized_query))
    latest_rows = _load_csv_rows(latest_path)
    archive_rows = _load_csv_rows(archive_path)
    merged = _merge_latest_archive(latest_rows, archive_rows)

    filtered = [
        row for row in merged
        if (
            needle in row["tradingsymbol"]
            or needle in str(row.get("name", "")).upper()
            or normalized_query in _text_key(str(row.get("tradingsymbol", "")))
            or normalized_query in _text_key(str(row.get("name", "")))
            or str(row.get("tradingsymbol", "")).upper() in alias_targets
        )
    ]
    filtered.sort(key=lambda row: _search_rank(row, q, normalized_query))
    items: list[dict[str, Any]] = []
    for row in filtered[:limit]:
        available_from, available_to = _availability_window(row)
        item = dict(row)
        item["available_from"] = available_from
        item["available_to"] = available_to
        items.append(item)
    return {"items": items, "source": "mapper_csv", "warning": None}


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_MAPPER_REQUIRED)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in _MAPPER_REQUIRED})


def _write_metadata(rows_latest: int, rows_archive: int) -> None:
    path = _metadata_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        "{\n"
        f'  "last_updated": "{date.today().isoformat()}",\n'
        f'  "rows_latest": {rows_latest},\n'
        f'  "rows_archive": {rows_archive}\n'
        "}\n"
    )
    path.write_text(payload, encoding="utf-8")


def update_mapper_from_zerodha() -> dict[str, Any]:
    api_key = (settings.ZERODHA_API_KEY or "").strip()
    access_token = (settings.ZERODHA_ACCESS_TOKEN or "").strip()
    if not api_key or not access_token:
        raise RuntimeError("Zerodha credentials missing. Login and generate access token first.")

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    fetched = kite.instruments()

    latest_rows_raw: list[dict[str, Any]] = []
    for raw in fetched:
        row = _normalize_row(raw)
        if row is not None:
            latest_rows_raw.append(row)

    latest_rows = _merge_latest_archive(latest_rows_raw, [])

    archive_existing = _load_csv_rows(_archive_csv_path())
    archive_merged = _merge_latest_archive(latest_rows, archive_existing)

    _write_csv(_latest_csv_path(), latest_rows)
    _write_csv(_archive_csv_path(), archive_merged)
    _write_metadata(len(latest_rows), len(archive_merged))

    return {
        "status": "updated",
        "rows_latest": len(latest_rows),
        "rows_archive": len(archive_merged),
        "latest_path": str(_latest_csv_path()),
        "archive_path": str(_archive_csv_path()),
    }


async def find_by_token(token: int) -> dict[str, Any] | None:
    db = get_db()
    return await db.instruments.find_one({"instrument_token": token})


async def find_by_symbol(symbol: str) -> dict[str, Any] | None:
    db = get_db()
    return await db.instruments.find_one(
        {"tradingsymbol": {"$regex": f"^{symbol}$", "$options": "i"}}
    )


async def search(query: str, limit: int = 50) -> list[dict[str, Any]]:
    """Search instruments by tradingsymbol (case-insensitive partial match)."""
    db = get_db()
    cursor = db.instruments.find(
        {"tradingsymbol": {"$regex": query, "$options": "i"}},
    ).limit(limit)
    return await cursor.to_list(length=limit)


async def get_all_equity() -> list[dict[str, Any]]:
    db = get_db()
    cursor = db.instruments.find(
        {"segment": "NSE", "instrument_type": "EQ"}
    )
    return await cursor.to_list(length=None)


async def search_with_fallback(query: str, limit: int = 50) -> dict[str, Any]:
    """Search MongoDB instruments first, fallback to mapper latest+archive CSV."""
    db = get_db()
    mongo_count = await db.instruments.count_documents({})
    q = query.strip()
    if not q:
        return {"items": [], "source": "none", "warning": "Empty search query."}

    if mongo_count > 0:
        items = await search(q, limit)
        return {"items": items, "source": "mongo", "warning": None}

    response = search_mapper_files(q, limit)
    response["warning"] = response.get("warning") or "MongoDB instruments empty. Using mapper CSV files."
    return response
