"""
One-time migration: zerodha_instruments_latest.csv → MongoDB instruments collection.

Run via Docker:
    docker compose run --rm -v ./Data:/app/Data backend python scripts/seed_instruments.py

After verification, delete CSV:
    rm Data/instrument_mapper_data/zerodha_instruments_latest.csv
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pymongo import MongoClient, ReplaceOne

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import settings

BATCH_SIZE = 1000


def main():
    csv_path = PROJECT_ROOT / "Data" / "instrument_mapper_data" / "zerodha_instruments_latest.csv"
    if not csv_path.is_file():
        print(f"[seed_instruments] CSV not found: {csv_path}")
        print("[seed_instruments] Instruments may already be seeded. Exiting.")
        return

    df = pd.read_csv(csv_path, low_memory=False)
    if df.empty:
        print("[seed_instruments] CSV is empty. Exiting.")
        return

    print(f"[seed_instruments] Loaded {len(df)} instruments from CSV")

    client = MongoClient(settings.MONGO_URI)
    db = client.get_default_database()

    # Create indexes
    db.instruments.create_index("instrument_token", unique=True, name="idx_instruments_token")
    db.instruments.create_index("tradingsymbol", name="idx_instruments_symbol")

    now = datetime.now(timezone.utc)
    operations = []

    for _, row in df.iterrows():
        try:
            token = int(row["instrument_token"])
        except (ValueError, TypeError, KeyError):
            continue

        doc = {
            "instrument_token": token,
            "tradingsymbol": str(row.get("tradingsymbol", "")).strip(),
            "exchange": str(row.get("exchange", "")).strip(),
            "segment": str(row.get("segment", "")).strip(),
            "instrument_type": str(row.get("instrument_type", "")).strip(),
            "strike": float(row["strike"]) if pd.notna(row.get("strike")) else None,
            "expiry": str(row["expiry"]) if pd.notna(row.get("expiry")) else None,
            "lot_size": int(row.get("lot_size", 1)) if pd.notna(row.get("lot_size")) else 1,
            "tick_size": float(row.get("tick_size", 0.05)) if pd.notna(row.get("tick_size")) else 0.05,
            "name": str(row.get("name", "")).strip() if pd.notna(row.get("name")) else "",
            "downloaded_at": now,
        }

        operations.append(
            ReplaceOne({"instrument_token": token}, doc, upsert=True)
        )

    # Bulk write
    total_upserted = 0
    for i in range(0, len(operations), BATCH_SIZE):
        batch = operations[i:i + BATCH_SIZE]
        result = db.instruments.bulk_write(batch, ordered=False)
        total_upserted += result.upserted_count + result.modified_count

    print(f"[seed_instruments] Seeded {total_upserted} instruments into MongoDB")
    print(f"[seed_instruments] Total documents in instruments: {db.instruments.count_documents({})}")
    client.close()


if __name__ == "__main__":
    main()
