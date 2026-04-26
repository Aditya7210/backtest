from __future__ import annotations

from datetime import datetime, time, timedelta
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
    INTERVAL_TO_MINUTES = {
        "minute": 1,
        "3minute": 3,
        "5minute": 5,
        "10minute": 10,
        "15minute": 15,
        "30minute": 30,
        "60minute": 60,
        "day": 24 * 60,
    }

    MAX_RETRIES = 5
    MAX_GAP_REFETCH_PASSES = 2
    MAX_GAP_SEGMENTS_PER_PASS = 500
    EMPTY_CHUNK_THRESHOLD = 0.7
    MAX_ALLOWED_CHUNKS = 500
    IST_TIMEZONE = "Asia/Kolkata"
    MARKET_OPEN_TIME = time(9, 15)
    MARKET_CLOSE_TIME = time(15, 30)

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
        enforce_market_hours: bool = True,
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
        loop_end_exclusive = end + timedelta(seconds=1)
        all_rows: list[dict[str, Any]] = []
        chunk_count = 0
        empty_chunk_count = 0

        while current_start < loop_end_exclusive:
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

            next_start = current_end + timedelta(seconds=1)
            if next_start <= current_start:
                raise RuntimeError(
                    "Chunk iterator stalled. Check chunk boundary increment logic."
                )
            current_start = next_start

        if (
            chunk_count > 0
            and (empty_chunk_count / chunk_count) > self.EMPTY_CHUNK_THRESHOLD
        ):
            raise RuntimeError("Too many empty chunks returned - possible API/data issue")

        if not all_rows:
            raise RuntimeError("No data returned for given inputs")

        data_df = self._normalize_dataframe(
            all_rows,
            include_oi=oi,
            interval=interval,
            enforce_market_hours=enforce_market_hours,
        )
        data_df = data_df.sort_index()
        data_df = data_df[~data_df.index.duplicated(keep="first")]

        expected_index = self._build_expected_index(
            start=start,
            end=end,
            interval=interval,
            observed_index=data_df.index,
        )
        self._log_coverage_stats(
            stage="initial",
            expected_index=expected_index,
            actual_index=data_df.index,
            requested_start=start,
            requested_end=end,
            interval=interval,
        )

        missing_index = self._detect_missing_timestamps(
            expected_index=expected_index,
            actual_index=data_df.index,
        )
        if not missing_index.empty:
            print(
                "[Coverage] missing timestamps detected: "
                f"{len(missing_index)} (first={missing_index.min()}, last={missing_index.max()})"
            )

        if missing_index.empty:
            return data_df

        all_rows_with_refetch = list(all_rows)
        for pass_index in range(self.MAX_GAP_REFETCH_PASSES):
            if missing_index.empty:
                break

            missing_segments = self._missing_timestamps_to_segments(
                missing_index=missing_index,
                interval=interval,
            )
            if not missing_segments:
                break

            if len(missing_segments) > self.MAX_GAP_SEGMENTS_PER_PASS:
                missing_segments = missing_segments[: self.MAX_GAP_SEGMENTS_PER_PASS]

            refetched_rows: list[dict[str, Any]] = []
            for segment_start_ist, segment_end_ist in missing_segments:
                from_dt = segment_start_ist.tz_localize(None).to_pydatetime()
                to_dt = segment_end_ist.tz_localize(None).to_pydatetime()
                if from_dt > to_dt:
                    continue

                segment_rows = self._fetch_with_retry(
                    instrument_token=instrument_token,
                    from_date=from_dt,
                    to_date=to_dt,
                    interval=interval,
                    continuous=continuous,
                    oi=oi,
                )
                if segment_rows:
                    refetched_rows.extend(segment_rows)

            if not refetched_rows:
                break

            all_rows_with_refetch.extend(refetched_rows)
            data_df = self._normalize_dataframe(
                all_rows_with_refetch,
                include_oi=oi,
                interval=interval,
                enforce_market_hours=enforce_market_hours,
            )
            data_df = data_df.sort_index()
            data_df = data_df[~data_df.index.duplicated(keep="first")]

            missing_index = self._detect_missing_timestamps(
                expected_index=expected_index,
                actual_index=data_df.index,
            )
            self._log_coverage_stats(
                stage=f"refetch-pass-{pass_index + 1}",
                expected_index=expected_index,
                actual_index=data_df.index,
                requested_start=start,
                requested_end=end,
                interval=interval,
            )
            if not missing_index.empty:
                print(
                    "[Coverage] remaining missing timestamps: "
                    f"{len(missing_index)} (first={missing_index.min()}, last={missing_index.max()})"
                )

        if not missing_index.empty:
            print(
                "[Coverage] gap refill incomplete after max passes; "
                f"remaining_missing={len(missing_index)}"
            )

        self._assert_dataset_integrity(
            df=data_df,
            requested_start=start,
            requested_end=end,
            interval=interval,
            expected_index=expected_index,
        )

        return data_df

    def _get_chunk_days(self, interval: str) -> int:
        if interval not in self.INTERVAL_CHUNK_DAYS:
            raise ValueError(
                f"Unsupported interval for chunking: {interval}. "
                f"Supported: {sorted(self.INTERVAL_CHUNK_DAYS)}"
            )
        return self.INTERVAL_CHUNK_DAYS[interval]

    @classmethod
    def interval_to_timedelta(cls, interval: str) -> timedelta:
        normalized_interval = str(interval or "").strip().lower()
        if normalized_interval not in cls.INTERVAL_TO_MINUTES:
            raise ValueError(
                f"Unsupported interval: {interval}. "
                f"Supported: {sorted(cls.INTERVAL_TO_MINUTES)}"
            )
        return timedelta(minutes=cls.INTERVAL_TO_MINUTES[normalized_interval])

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
        interval: str,
        enforce_market_hours: bool,
    ) -> pd.DataFrame:
        if not rows:
            columns = ["Open", "High", "Low", "Close", "Volume"]
            if include_oi:
                columns.append("OI")
            empty_df = pd.DataFrame(columns=columns)
            empty_df.index = pd.DatetimeIndex([], name="Date", tz=self.IST_TIMEZONE)
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

        df["Date"] = pd.to_datetime(df["Date"], errors="coerce", utc=True)
        df = df.dropna(subset=["Date"])
        df = df.set_index("Date")
        df.index = self._to_ist_index(df.index)
        df = df.sort_index()
        df = df[~df.index.duplicated(keep="first")]

        if enforce_market_hours and interval != "day":
            df = self._apply_market_hour_filter(df)
            self._assert_market_hours(df.index)
        elif not enforce_market_hours:
            print("[Zerodha] market hour filter skipped")

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

    def _build_expected_index(
        self,
        *,
        start: datetime,
        end: datetime,
        interval: str,
        observed_index: pd.DatetimeIndex,
    ) -> pd.DatetimeIndex:
        if interval == "day":
            return pd.DatetimeIndex([], tz=self.IST_TIMEZONE)
        if observed_index.empty:
            return pd.DatetimeIndex([], tz=self.IST_TIMEZONE)

        expected_start = self._to_ist_timestamp(start)
        expected_end = self._to_ist_timestamp(end)
        if expected_start > expected_end:
            return pd.DatetimeIndex([], tz=self.IST_TIMEZONE)

        interval_delta = self.interval_to_timedelta(interval)
        observed_days = sorted({ts.normalize() for ts in observed_index})
        if not observed_days:
            return pd.DatetimeIndex([], tz=self.IST_TIMEZONE)

        expected_ranges: list[pd.DatetimeIndex] = []
        for day_start in observed_days:
            if day_start.weekday() >= 5:
                continue
            session_start = day_start + timedelta(
                hours=self.MARKET_OPEN_TIME.hour,
                minutes=self.MARKET_OPEN_TIME.minute,
            )
            session_end = day_start + timedelta(
                hours=self.MARKET_CLOSE_TIME.hour,
                minutes=self.MARKET_CLOSE_TIME.minute,
            )

            bounded_start = max(session_start, expected_start)
            bounded_end = min(session_end, expected_end)
            if bounded_start > bounded_end:
                continue

            aligned_start = self._align_timestamp_up(bounded_start, interval_delta)
            aligned_end = self._align_timestamp_down(bounded_end, interval_delta)
            if aligned_start > aligned_end:
                continue

            expected_ranges.append(
                pd.date_range(
                    start=aligned_start,
                    end=aligned_end,
                    freq=interval_delta,
                    tz=self.IST_TIMEZONE,
                )
            )

        if not expected_ranges:
            return pd.DatetimeIndex([], tz=self.IST_TIMEZONE)

        expected_index = expected_ranges[0]
        for idx in expected_ranges[1:]:
            expected_index = expected_index.union(idx)
        return expected_index

    def _detect_missing_timestamps(
        self,
        *,
        expected_index: pd.DatetimeIndex,
        actual_index: pd.DatetimeIndex,
    ) -> pd.DatetimeIndex:
        if expected_index.empty:
            return pd.DatetimeIndex([], tz=self.IST_TIMEZONE)
        return expected_index.difference(actual_index)

    def _missing_timestamps_to_segments(
        self,
        *,
        missing_index: pd.DatetimeIndex,
        interval: str,
    ) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
        if missing_index.empty:
            return []

        interval_delta = self.interval_to_timedelta(interval)
        sorted_missing = missing_index.sort_values()
        segments: list[tuple[pd.Timestamp, pd.Timestamp]] = []

        segment_start = sorted_missing[0]
        previous_ts = sorted_missing[0]
        for ts in sorted_missing[1:]:
            if (ts - previous_ts) > interval_delta:
                segments.append((segment_start, previous_ts))
                segment_start = ts
            previous_ts = ts
        segments.append((segment_start, previous_ts))
        return segments

    def _log_coverage_stats(
        self,
        *,
        stage: str,
        expected_index: pd.DatetimeIndex,
        actual_index: pd.DatetimeIndex,
        requested_start: datetime,
        requested_end: datetime,
        interval: str,
    ) -> None:
        expected_count = int(len(expected_index))
        actual_count = int(len(actual_index))
        print(
            f"[Coverage:{stage}] interval={interval} expected={expected_count} actual={actual_count}"
        )

        expected_start_ist = self._to_ist_timestamp(requested_start)
        expected_end_ist = self._to_ist_timestamp(requested_end)
        if interval != "day":
            expected_start_ist = max(
                expected_start_ist,
                expected_start_ist.normalize()
                + timedelta(
                    hours=self.MARKET_OPEN_TIME.hour,
                    minutes=self.MARKET_OPEN_TIME.minute,
                ),
            )
            expected_end_ist = min(
                expected_end_ist,
                expected_end_ist.normalize()
                + timedelta(
                    hours=self.MARKET_CLOSE_TIME.hour,
                    minutes=self.MARKET_CLOSE_TIME.minute,
                ),
            )

        if actual_count > 0:
            actual_start = actual_index.min()
            actual_end = actual_index.max()
            print(
                f"[Coverage:{stage}] first={actual_start} last={actual_end}"
            )
            if actual_start != expected_start_ist:
                print(
                    "[Coverage] start mismatch: "
                    f"expected_start={expected_start_ist}, actual_start={actual_start}"
                )
            if interval == "day":
                end_tolerance = timedelta(days=1)
            else:
                end_tolerance = self.interval_to_timedelta(interval)
            if actual_end + end_tolerance < expected_end_ist:
                print(
                    "[Coverage] end coverage warning: "
                    f"expected_end={expected_end_ist}, actual_end={actual_end}, "
                    f"tolerance={end_tolerance}"
                )
        else:
            print("[Coverage] actual dataset is empty after normalization")

    def _to_ist_timestamp(self, value: datetime) -> pd.Timestamp:
        ts = pd.Timestamp(value)
        if ts.tzinfo is None:
            # Naive datetimes from UI/service are treated as already in IST.
            ts = ts.tz_localize(self.IST_TIMEZONE)
        else:
            ts = ts.tz_convert(self.IST_TIMEZONE)
        return ts

    def _align_timestamp_up(
        self,
        value: pd.Timestamp,
        interval_delta: timedelta,
    ) -> pd.Timestamp:
        step_seconds = max(1, int(interval_delta.total_seconds()))
        day_start = value.normalize()
        elapsed_seconds = (value - day_start).total_seconds()
        aligned_seconds = int(((elapsed_seconds + step_seconds - 1) // step_seconds) * step_seconds)
        return day_start + pd.Timedelta(seconds=aligned_seconds)

    def _align_timestamp_down(
        self,
        value: pd.Timestamp,
        interval_delta: timedelta,
    ) -> pd.Timestamp:
        step_seconds = max(1, int(interval_delta.total_seconds()))
        day_start = value.normalize()
        elapsed_seconds = (value - day_start).total_seconds()
        aligned_seconds = int((elapsed_seconds // step_seconds) * step_seconds)
        return day_start + pd.Timedelta(seconds=aligned_seconds)

    def _apply_market_hour_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        return df.between_time(
            self.MARKET_OPEN_TIME.strftime("%H:%M"),
            self.MARKET_CLOSE_TIME.strftime("%H:%M"),
        )

    def _assert_market_hours(self, index: pd.DatetimeIndex) -> None:
        if index.empty:
            return
        index_times = pd.Series(index.time)
        valid = (
            (index_times >= self.MARKET_OPEN_TIME)
            & (index_times <= self.MARKET_CLOSE_TIME)
        )
        if not bool(valid.all()):
            raise RuntimeError(
                "Detected timestamps outside market hours (09:15 to 15:30 IST)"
            )

    def _to_ist_index(self, index: pd.Index) -> pd.DatetimeIndex:
        parsed_values: list[pd.Timestamp] = []
        timezone_flags: list[bool] = []
        for raw_value in list(index):
            parsed = pd.to_datetime(raw_value, errors="coerce")
            if pd.isna(parsed):
                continue
            ts = pd.Timestamp(parsed)
            parsed_values.append(ts)
            timezone_flags.append(ts.tzinfo is not None)

        if not parsed_values:
            return pd.DatetimeIndex([], tz=self.IST_TIMEZONE)

        has_aware = any(timezone_flags)
        has_naive = any(not flag for flag in timezone_flags)
        if has_aware and has_naive:
            raise RuntimeError("Mixed timezone index detected in Zerodha data")

        if has_aware:
            converted_values = [ts.tz_convert(self.IST_TIMEZONE) for ts in parsed_values]
            print("[Zerodha] timezone detected: aware -> converted to IST")
        else:
            converted_values = [ts.tz_localize(self.IST_TIMEZONE) for ts in parsed_values]
            print("[Zerodha] timezone detected: naive -> assumed IST")

        converted = pd.DatetimeIndex(converted_values)
        if converted.tz is None:
            raise RuntimeError("Timezone normalization failed for Zerodha data")
        return converted

    def _assert_dataset_integrity(
        self,
        *,
        df: pd.DataFrame,
        requested_start: datetime,
        requested_end: datetime,
        interval: str,
        expected_index: pd.DatetimeIndex,
    ) -> None:
        if df.empty:
            raise RuntimeError("Zerodha dataset is empty after fetch/merge")
        if not isinstance(df.index, pd.DatetimeIndex):
            raise RuntimeError("Zerodha dataset index must be DatetimeIndex")
        if not bool(df.index.is_monotonic_increasing):
            raise RuntimeError("Zerodha dataset index is not monotonic increasing")
        if bool(df.index.duplicated().any()):
            raise RuntimeError("Zerodha dataset contains duplicate timestamps")

        missing_index = self._detect_missing_timestamps(
            expected_index=expected_index,
            actual_index=df.index,
        )
        print(f"[Coverage] missing timestamps count={len(missing_index)}")

        actual_start = df.index.min()
        actual_end = df.index.max()
        expected_start = self._to_ist_timestamp(requested_start)
        expected_end = self._to_ist_timestamp(requested_end)

        if interval != "day":
            expected_start = max(
                expected_start,
                expected_start.normalize()
                + timedelta(
                    hours=self.MARKET_OPEN_TIME.hour,
                    minutes=self.MARKET_OPEN_TIME.minute,
                ),
            )
            expected_end = min(
                expected_end,
                expected_end.normalize()
                + timedelta(
                    hours=self.MARKET_CLOSE_TIME.hour,
                    minutes=self.MARKET_CLOSE_TIME.minute,
                ),
            )
            tolerance = self.interval_to_timedelta(interval)
        else:
            tolerance = timedelta(days=1)

        if actual_start > expected_start + tolerance:
            print(
                "[Coverage] start boundary warning: "
                f"expected~={expected_start}, actual={actual_start}, tolerance={tolerance}"
            )
        if actual_end + tolerance < expected_end:
            print(
                "[Coverage] end boundary warning: "
                f"expected>={expected_end}, actual={actual_end}, tolerance={tolerance}"
            )

    @staticmethod
    def _validate_datetime(value: datetime, field_name: str) -> datetime:
        if not isinstance(value, datetime):
            raise ValueError(f"{field_name} must be a datetime instance")
        return value
