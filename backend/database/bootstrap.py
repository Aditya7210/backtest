"""Database bootstrap helpers (indexes and cache collections)."""
from __future__ import annotations

from pymongo import ASCENDING, DESCENDING

from backend.database.connection import get_db


async def ensure_core_indexes() -> None:
    """Create required indexes for ingest/query performance."""
    db = get_db()

    # Bars collection: ingest writes and backtest/catalog reads.
    await db.bars.create_index(
        [("instrument_token", ASCENDING), ("timeframe", ASCENDING), ("timestamp", ASCENDING)],
        unique=True,
        name="uniq_token_tf_ts",
        background=True,
    )
    await db.bars.create_index(
        [("instrument_token", ASCENDING), ("timeframe", ASCENDING), ("trading_date", ASCENDING), ("timestamp", ASCENDING)],
        name="idx_token_tf_trading_date_ts",
        background=True,
    )
    await db.bars.create_index(
        [("ingest_job_id", ASCENDING)],
        name="idx_ingest_job_id",
        background=True,
    )
    await db.bars.create_index(
        [("timeframe", ASCENDING), ("trading_date", ASCENDING), ("instrument_type", ASCENDING)],
        name="idx_tf_trading_date_inst_type",
        background=True,
    )
    await db.bars.create_index(
        [("tradingsymbol", ASCENDING), ("timeframe", ASCENDING)],
        name="idx_tradingsymbol_tf",
        background=True,
    )

    # Ingest job metadata collection.
    await db.historical_ingest_jobs.create_index(
        [("job_id", ASCENDING)],
        unique=True,
        name="uniq_job_id",
        background=True,
    )
    await db.historical_ingest_jobs.create_index(
        [("status", ASCENDING), ("updated_at", DESCENDING)],
        name="idx_status_updated_at_desc",
        background=True,
    )

    # Materialized catalog cache.
    await db.historical_catalog.create_index(
        [("instrument_token", ASCENDING)],
        unique=True,
        name="uniq_catalog_token",
        background=True,
    )
    await db.historical_catalog.create_index(
        [("tradingsymbol", ASCENDING)],
        name="idx_catalog_symbol",
        background=True,
    )

