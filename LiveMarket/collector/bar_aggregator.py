from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Any
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")


@dataclass
class CompletedBar:
    instrument_token: int
    bar_start: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    oi: float


class MinuteBarAggregator:
    def __init__(self) -> None:
        self._bars: dict[int, dict[str, Any]] = {}
        self._first_minute_seen: dict[int, datetime] = {}
        self._pending_completed: list[CompletedBar] = []
        self._lock = Lock()

    @staticmethod
    def _to_ist_minute_start(value: datetime) -> datetime:
        if value.tzinfo is None:
            ts = value.replace(tzinfo=IST)
        else:
            ts = value.astimezone(IST)
        return ts.replace(second=0, microsecond=0)

    def update(
        self,
        token: int,
        ltp: float,
        session_volume: float | int | None,
        oi: float | int | None,
        tick_time: datetime,
    ) -> None:
        token_int = int(token)
        price = float(ltp or 0.0)
        session_volume_value = float(session_volume or 0.0)
        oi_value = float(oi or 0.0)
        minute_start = self._to_ist_minute_start(tick_time)

        with self._lock:
            state = self._bars.get(token_int)
            if state is None:
                self._first_minute_seen.setdefault(token_int, minute_start)
                self._bars[token_int] = {
                    "bar_start": minute_start,
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "volume": 0.0,
                    "oi": oi_value,
                    "prev_session_volume": session_volume_value,
                }
                return

            state_minute = state["bar_start"]
            if minute_start > state_minute:
                first_minute = self._first_minute_seen.get(token_int)
                if first_minute is None or first_minute != state_minute:
                    self._pending_completed.append(
                        CompletedBar(
                            instrument_token=token_int,
                            bar_start=state_minute,
                            open=float(state["open"]),
                            high=float(state["high"]),
                            low=float(state["low"]),
                            close=float(state["close"]),
                            volume=float(state["volume"]),
                            oi=float(state["oi"]),
                        )
                    )
                # New minute: initialize with fresh bar.
                self._bars[token_int] = {
                    "bar_start": minute_start,
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "volume": 0.0,
                    "oi": oi_value,
                    "prev_session_volume": session_volume_value,
                }
                return

            if minute_start < state_minute:
                # Out-of-order stale tick; ignore.
                return

            prev_session = float(state.get("prev_session_volume") or 0.0)
            volume_delta = session_volume_value - prev_session
            if volume_delta < 0:
                volume_delta = 0.0

            state["high"] = max(float(state["high"]), price)
            state["low"] = min(float(state["low"]), price)
            state["close"] = price
            state["volume"] = float(state["volume"]) + volume_delta
            state["oi"] = oi_value
            state["prev_session_volume"] = session_volume_value

    def close_bar(self, token: int, minute_start: datetime) -> CompletedBar | None:
        token_int = int(token)
        minute = self._to_ist_minute_start(minute_start)
        with self._lock:
            state = self._bars.get(token_int)
            if state is None:
                return None
            if state["bar_start"] != minute:
                return None
            first_minute = self._first_minute_seen.get(token_int)
            if first_minute is not None and first_minute == state["bar_start"]:
                self._bars.pop(token_int, None)
                return None
            bar = CompletedBar(
                instrument_token=token_int,
                bar_start=state["bar_start"],
                open=float(state["open"]),
                high=float(state["high"]),
                low=float(state["low"]),
                close=float(state["close"]),
                volume=float(state["volume"]),
                oi=float(state["oi"]),
            )
            self._bars.pop(token_int, None)
            return bar

    def get_completed_bars(self, current_minute: datetime) -> list[CompletedBar]:
        boundary = self._to_ist_minute_start(current_minute)
        completed: list[CompletedBar] = []
        with self._lock:
            if self._pending_completed:
                completed.extend(self._pending_completed)
                self._pending_completed = []
            to_finalize = [
                token
                for token, state in self._bars.items()
                if state["bar_start"] < boundary
            ]
            for token in to_finalize:
                state = self._bars.pop(token, None)
                if state is None:
                    continue
                first_minute = self._first_minute_seen.get(token)
                if first_minute is not None and first_minute == state["bar_start"]:
                    continue
                completed.append(
                    CompletedBar(
                        instrument_token=int(token),
                        bar_start=state["bar_start"],
                        open=float(state["open"]),
                        high=float(state["high"]),
                        low=float(state["low"]),
                        close=float(state["close"]),
                        volume=float(state["volume"]),
                        oi=float(state["oi"]),
                    )
                )
        return completed


__all__ = ["CompletedBar", "MinuteBarAggregator", "IST"]
