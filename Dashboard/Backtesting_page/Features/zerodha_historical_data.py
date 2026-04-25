from __future__ import annotations

from datetime import datetime, timedelta
from time import sleep
from typing import Any

import pandas as pd
from kiteconnect import KiteConnect


class ZerodhaHistoricalData:
    SUPPORTED_INTERVALS = {
        "minute",
        "3minute",
        "5minute",
        "10minute",
        "15minute",
        "30minute",
        "60minute",
        "day",
    }

    INTERVAL_CHUNK_DAYS = {
        "minute": 60,
        "3minute": 90,
        "5minute": 100,
        "10minute": 120,
        "15minute": 150,
        "30minute": 200,
        "60minute": 400,
        "day": 2000,
    }

    MAX_RETRIES = 5
    EMPTY_CHUNK_THRESHOLD = 0.7
    MAX_ALLOWED_CHUNKS = 500

    def __init__(self, api_key: str, access_token: str) -> None:
        self._kite = KiteConnect(api_key=api_key)
        self._kite.set_access_token(access_token)

    def fetch_data(
        self,
        instrument_token: int,
        from_date: datetime,
        to_date: datetime,
        interval: str,
        continuous: bool = False,
        oi: bool = False,
        debug: bool = False,
    ) -> pd.DataFrame:
        start = self._validate_datetime(from_date, "from_date")
        end = self._validate_datetime(to_date, "to_date")

        if start >= end:
            raise ValueError("from_date must be earlier than to_date")

        if interval not in self.SUPPORTED_INTERVALS:
            raise ValueError(
                f"Invalid interval: {interval}. "
                f"Supported: {sorted(self.SUPPORTED_INTERVALS)}"
            )

        chunk_days = self._get_chunk_days(interval)
        chunk_span_seconds = chunk_days * 24 * 60 * 60
        total_span_seconds = int((end - start).total_seconds()) + 1
        estimated_chunks = (total_span_seconds + chunk_span_seconds - 1) // chunk_span_seconds
        if estimated_chunks > self.MAX_ALLOWED_CHUNKS:
            raise RuntimeError(
                "Requested data range too large. Reduce date range or interval."
            )

        current_start = start
        all_rows: list[dict[str, Any]] = []
        chunk_count = 0
        empty_chunk_count = 0

        while current_start <= end:
            current_end = min(
                current_start + timedelta(days=chunk_days) - timedelta(seconds=1),
                end,
            )
            chunk_count += 1

            if debug:
                print(f"Fetching chunk: {current_start} -> {current_end}")

            chunk_rows = self._fetch_with_retry(
                instrument_token=instrument_token,
                from_date=current_start,
                to_date=current_end,
                interval=interval,
                continuous=continuous,
                oi=oi,
            )
            if chunk_rows:
                all_rows.extend(chunk_rows)
            else:
                empty_chunk_count += 1

            current_start = current_end + timedelta(seconds=1)

        if (
            chunk_count > 0
            and (empty_chunk_count / chunk_count) > self.EMPTY_CHUNK_THRESHOLD
        ):
            raise RuntimeError("Too many empty chunks returned — possible API/data issue")

        if not all_rows:
            raise RuntimeError("No data returned for given inputs")

        return self._normalize_dataframe(all_rows, include_oi=oi)

    def _get_chunk_days(self, interval: str) -> int:
        if interval not in self.INTERVAL_CHUNK_DAYS:
            raise ValueError(
                f"Unsupported interval for chunking: {interval}. "
                f"Supported: {sorted(self.INTERVAL_CHUNK_DAYS)}"
            )
        return self.INTERVAL_CHUNK_DAYS[interval]

    def _fetch_with_retry(
        self,
        *,
        instrument_token: int,
        from_date: datetime,
        to_date: datetime,
        interval: str,
        continuous: bool,
        oi: bool,
    ) -> list[dict[str, Any]]:
        last_exception: Exception | None = None

        for attempt in range(self.MAX_RETRIES):
            if attempt > 0:
                sleep(min(2 ** attempt, 8))

            try:
                print("Fetching Zerodha data with:")
                print("Instrument:", instrument_token)
                print("From:", from_date)
                print("To:", to_date)
                print("Interval:", interval)
                data = self._kite.historical_data(
                    instrument_token=instrument_token,
                    from_date=from_date,
                    to_date=to_date,
                    interval=interval,
                    continuous=continuous,
                    oi=oi,
                )
                return data if isinstance(data, list) else []
            except Exception as e:
                print(f"[Zerodha Error] Attempt {attempt + 1} failed:")
                print("ERROR TYPE:", type(e).__name__)
                print("ERROR MESSAGE:", str(e))
                last_exception = e

        if last_exception is None:
            raise RuntimeError(
                f"Zerodha API failed after {self.MAX_RETRIES} retries. "
                "Last error: UnknownError: No exception captured"
            )

        raise RuntimeError(
            f"Zerodha API failed after {self.MAX_RETRIES} retries. "
            f"Last error: {type(last_exception).__name__}: {str(last_exception)}"
        ) from last_exception

    def _normalize_dataframe(
        self,
        rows: list[dict[str, Any]],
        *,
        include_oi: bool,
    ) -> pd.DataFrame:
        if not rows:
            columns = ["Open", "High", "Low", "Close", "Volume"]
            if include_oi:
                columns.append("OI")
            empty_df = pd.DataFrame(columns=columns)
            empty_df.index = pd.DatetimeIndex([], name="Date")
            return empty_df

        df = pd.DataFrame(rows)
        rename_map = {
            "date": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
            "oi": "OI",
        }
        df = df.rename(columns=rename_map)

        required_columns = ["Date", "Open", "High", "Low", "Close", "Volume"]
        missing_required = [col for col in required_columns if col not in df.columns]
        if missing_required:
            raise RuntimeError(
                f"Zerodha response missing required columns: {missing_required}"
            )

        if include_oi and "OI" not in df.columns:
            df["OI"] = pd.NA

        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date"])
        df = df.set_index("Date")
        df = df.sort_index()
        df = df[~df.index.duplicated(keep="first")]

        numeric_columns = ["Open", "High", "Low", "Close", "Volume"]
        if "OI" in df.columns:
            numeric_columns.append("OI")

        for column in numeric_columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

        df = df.dropna(subset=["Open", "High", "Low", "Close"])

        ordered_columns = ["Open", "High", "Low", "Close", "Volume"]
        if "OI" in df.columns:
            ordered_columns.append("OI")

        return df[ordered_columns]

    @staticmethod
    def _validate_datetime(value: datetime, field_name: str) -> datetime:
        if not isinstance(value, datetime):
            raise ValueError(f"{field_name} must be a datetime instance")
        return value
