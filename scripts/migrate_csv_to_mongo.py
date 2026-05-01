"""
One-time migration: existing live-market CSVs → MongoDB bars collection.

Run via Docker:
    docker compose run --rm -v ./Data:/app/Data backend python scripts/migrate_csv_to_mongo.py

After verification, delete CSVs: rm -rf Data/live_market/daily/
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pymongo import MongoClient, ReplaceOne

# Resolve project root and add to path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import settings

BATCH_SIZE = 1000


def _parse_instrument_type(filename: str) -> str:
    stem = filename.lower()
    if stem.startswith("equities"):
        return "equity"
    if stem.startswith("options"):
        return "option"
    if stem.startswith("vix"):
        return "vix"
    return "unknown"


def _parse_timeframe(filename: str) -> str:
    # e.g. equities_1min.csv → 1min, equities_5min.csv → 5min
    stem = Path(filename).stem
    parts = stem.split("_")
    for part in parts:
        if part.endswith("min"):
            return part
    return "1min"


def _to_utc(ts: pd.Timestamp) -> datetime:
    if ts.tzinfo is None:
        # Assume IST if naive
        ts = ts.tz_localize("Asia/Kolkata")
    return ts.tz_convert("UTC").to_pydatetime().replace(tzinfo=timezone.utc)


def migrate_csv(csv_path: Path, trading_date: str, db) -> dict:
    """Migrate a single CSV file to MongoDB bars collection."""
    filename = csv_path.name
    instrument_type = _parse_instrument_type(filename)
    timeframe = _parse_timeframe(filename)

    df = pd.read_csv(csv_path)
    if df.empty:
        return {"file": str(csv_path), "rows": 0, "inserted": 0, "skipped": 0}

    if "timestamp" not in df.columns:
        return {"file": str(csv_path), "rows": 0, "inserted": 0, "skipped": 0, "error": "no timestamp column"}

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])

    operations = []
    for _, row in df.iterrows():
        ts_utc = _to_utc(row["timestamp"])
        doc = {
            "timestamp": ts_utc,
            "trading_date": trading_date,
            "timeframe": timeframe,
            "instrument_type": instrument_type,
            "open": float(row.get("open", 0)),
            "high": float(row.get("high", 0)),
            "low": float(row.get("low", 0)),
            "close": float(row.get("close", 0)),
            "volume": float(row.get("volume", 0)) if "volume" in row.index else 0.0,
            "data_source": "live",
        }

        # Add instrument_token if present
        if "instrument_token" in row.index:
            try:
                doc["instrument_token"] = int(row["instrument_token"])
            except (ValueError, TypeError):
                doc["instrument_token"] = 0
        else:
            doc["instrument_token"] = 0

        # Add tradingsymbol if present
        if "tradingsymbol" in row.index:
            doc["tradingsymbol"] = str(row["tradingsymbol"])

        # Option-specific fields
        if instrument_type == "option":
            doc["strike"] = float(row.get("strike", 0)) if "strike" in row.index else None
            doc["expiry"] = str(row.get("expiry", "")) if "expiry" in row.index else None
            doc["option_type"] = str(row.get("option_type", "")) if "option_type" in row.index else None
            doc["oi"] = float(row.get("oi", 0)) if "oi" in row.index else None
        else:
            doc["strike"] = None
            doc["expiry"] = None
            doc["option_type"] = None
            doc["oi"] = float(row.get("oi", 0)) if "oi" in row.index else None

        filt = {
            "instrument_token": doc["instrument_token"],
            "timeframe": doc["timeframe"],
            "timestamp": doc["timestamp"],
        }
        operations.append(ReplaceOne(filt, doc, upsert=True))

    # Execute in batches
    inserted = 0
    for i in range(0, len(operations), BATCH_SIZE):
        batch = operations[i:i + BATCH_SIZE]
        result = db.bars.bulk_write(batch, ordered=False)
        inserted += result.upserted_count + result.modified_count

    return {
        "file": str(csv_path),
        "rows": len(df),
        "inserted": inserted,
        "skipped": len(df) - inserted,
    }


def main():
    client = MongoClient(settings.MONGO_URI)
    db = client.get_default_database()

    # Create indexes
    db.bars.create_index(
        [("instrument_token", 1), ("timeframe", 1), ("timestamp", 1)],
        unique=True,
        name="idx_bars_unique",
    )
    db.bars.create_index(
        [("instrument_token", 1), ("timeframe", 1), ("timestamp", -1)],
        name="idx_bars_primary_query",
    )
    db.bars.create_index(
        [("trading_date", 1), ("timeframe", 1), ("instrument_type", 1)],
        name="idx_bars_date_range",
    )
    db.bars.create_index(
        [("tradingsymbol", 1), ("timeframe", 1), ("timestamp", -1)],
        name="idx_bars_symbol_lookup",
    )
    print("[migrate] MongoDB indexes created on bars collection")

    daily_root = PROJECT_ROOT / "Data" / "live_market" / "daily"
    if not daily_root.exists():
        print(f"[migrate] No daily directory found at {daily_root}. Nothing to migrate.")
        return

    total_files = 0
    total_rows = 0
    total_inserted = 0

    for day_dir in sorted(daily_root.iterdir()):
        if not day_dir.is_dir():
            continue
        trading_date = day_dir.name
        print(f"\n[migrate] Processing {trading_date}...")

        for csv_file in sorted(day_dir.glob("*.csv")):
            result = migrate_csv(csv_file, trading_date, db)
            total_files += 1
            total_rows += result.get("rows", 0)
            total_inserted += result.get("inserted", 0)
            print(f"  {csv_file.name}: {result.get('rows', 0)} rows, {result.get('inserted', 0)} inserted")

    print(f"\n[migrate] DONE: {total_files} files, {total_rows} rows processed, {total_inserted} inserted/updated")
    client.close()


if __name__ == "__main__":
    main()
