"""FastAPI application factory with lifespan, CORS, and route mounting."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.database.connection import connect_db, close_db, get_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown events — connect MongoDB, reset stale status (E-07)."""
    await connect_db()

    # Reset collector/calculator status on startup (E-07: stale PID after restart)
    try:
        db = get_db()
        await db.collector_status.update_one(
            {"_id": "singleton"},
            {"$set": {
                "collector.status": "stopped",
                "calculator.status": "stopped",
            }},
            upsert=True,
        )
    except Exception as e:
        print(f"[startup] Failed to reset status: {e}")

    # Log Cython status (E-16)
    try:
        from backend.cython_math import compute_vwap_close
        print("[startup] Cython math kernels: ACTIVE")
    except Exception:
        print("[startup] Cython math kernels: FALLBACK (pure Python)")

    yield

    await close_db()


app = FastAPI(
    title="Algo Trading System",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS — dev only; in production nginx proxies same-origin (E-17)
origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
if origins and origins != ["none"]:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Mount REST routes
from backend.api.routes import market_data, historical_data, backtests, strategies, collector, auth, indicators

app.include_router(market_data.router, prefix="/api")
app.include_router(historical_data.router, prefix="/api")
app.include_router(backtests.router, prefix="/api")
app.include_router(strategies.router, prefix="/api")
app.include_router(collector.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(indicators.router, prefix="/api")

# Mount WebSocket endpoints
from backend.api.websocket.manager import ws_live_endpoint, ws_backtest_endpoint

app.add_api_websocket_route("/ws/live", ws_live_endpoint)
app.add_api_websocket_route("/ws/backtest/{task_id}", ws_backtest_endpoint)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
