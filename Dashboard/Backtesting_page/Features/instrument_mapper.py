from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
from kiteconnect import KiteConnect


class InstrumentMapper:
    _REQUIRED_COLUMNS = [
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

    def __init__(
        self,
        api_key: str,
        access_token: str,
        auto_update: bool = True,
    ) -> None:
        self._kite = KiteConnect(api_key=api_key)
        self._kite.set_access_token(access_token)

        self._storage_dir = (
            Path(__file__).resolve().parents[3] / "Data" / "instrument_mapper_data"
        )
        self._latest_path = self._storage_dir / "zerodha_instruments_latest.csv"
        self._archive_path = self._storage_dir / "zerodha_instruments_archive.csv"
        self._metadata_path = self._storage_dir / "metadata.json"

        self._storage_dir.mkdir(parents=True, exist_ok=True)

        self._latest_df = self._load_csv(self._latest_path)
        self._archive_df = self._load_csv(self._archive_path)
        self._metadata = self._load_metadata()
        self._combined_df = self._prepare_combined_df()

        if auto_update:
            self.auto_update_if_outdated()
            self._combined_df = self._prepare_combined_df()

    def auto_update_if_outdated(self) -> None:
        last_updated = str(self._metadata.get("last_updated", "")).strip()
        if last_updated != date.today().isoformat():
            self.update_instruments()

    def update_instruments(self) -> None:
        try:
            instruments = self._kite.instruments()
        except Exception as exc:
            raise RuntimeError("Failed to fetch instruments from Zerodha API") from exc

        latest_df = pd.DataFrame(instruments)
        latest_df = self._ensure_required_columns(latest_df)
        latest_df = self._normalize_dataframe(latest_df)

        latest_df.to_csv(self._latest_path, index=False)

        if self._archive_df.empty:
            archive_df = latest_df.copy()
        else:
            archive_df = pd.concat([self._archive_df, latest_df], ignore_index=True, sort=False)
            archive_df = self._ensure_required_columns(archive_df)
            archive_df = self._normalize_dataframe(archive_df)

        archive_df = self._deduplicate_archive(archive_df)
        archive_df.to_csv(self._archive_path, index=False)

        self._latest_df = latest_df
        self._archive_df = archive_df
        self._combined_df = self._prepare_combined_df()
        self._metadata = {
            "last_updated": date.today().isoformat(),
            "rows_latest": int(len(self._latest_df)),
            "rows_archive": int(len(self._archive_df)),
        }
        self._save_metadata()

    def get_token(
        self,
        symbol: str,
        exchange: str = "NSE",
        segment: str | None = None,
    ) -> int:
        normalized_symbol = (symbol or "").strip().upper()
        normalized_exchange = (exchange or "").strip().upper()
        normalized_segment = (segment or "").strip().upper() or None

        if not normalized_symbol:
            raise ValueError("Symbol cannot be empty")

        token = self._lookup_token(
            self._latest_df,
            symbol=normalized_symbol,
            exchange=normalized_exchange,
            segment=normalized_segment,
        )
        if token is not None:
            return token

        token = self._lookup_token(
            self._archive_df,
            symbol=normalized_symbol,
            exchange=normalized_exchange,
            segment=normalized_segment,
        )
        if token is not None:
            return token

        raise ValueError(f"Instrument not found for symbol: {normalized_symbol}")

    def search_symbol(self, query: str) -> list[dict[str, Any]]:
        normalized_query = (query or "").strip().upper()
        if not normalized_query:
            return []

        combined_df = self._combined_df
        if combined_df.empty:
            return []

        tradingsymbol_upper = combined_df["tradingsymbol"].astype(str).str.upper()
        name_upper = combined_df["name"].astype(str).str.upper()
        exact_matches = combined_df[tradingsymbol_upper == normalized_query]
        startswith_matches = combined_df[tradingsymbol_upper.str.startswith(normalized_query, na=False)]
        startswith_matches = startswith_matches[
            ~startswith_matches.index.isin(exact_matches.index)
        ]
        contains_matches = combined_df[
            tradingsymbol_upper.str.contains(normalized_query, na=False, regex=False)
            | name_upper.str.contains(normalized_query, na=False, regex=False)
        ]
        contains_matches = contains_matches[
            ~contains_matches.index.isin(exact_matches.index)
            & ~contains_matches.index.isin(startswith_matches.index)
        ]
        matches = pd.concat(
            [exact_matches, startswith_matches, contains_matches],
            ignore_index=True,
            sort=False,
        )
        matches = matches.drop_duplicates(subset=["instrument_token"], keep="first")

        if matches.empty:
            return []

        result_columns = [
            "instrument_token",
            "tradingsymbol",
            "name",
            "exchange",
            "segment",
            "expiry",
            "instrument_type",
            "lot_size",
        ]
        limited = matches.head(25)[result_columns]
        return limited.to_dict(orient="records")

    def _lookup_token(
        self,
        df: pd.DataFrame,
        *,
        symbol: str,
        exchange: str,
        segment: str | None,
    ) -> int | None:
        if df.empty:
            return None

        work_df = self._ensure_required_columns(df)

        exchange_mask = work_df["exchange"].astype(str).str.upper() == exchange
        tradingsymbol_upper = work_df["tradingsymbol"].astype(str).str.upper()
        exact_filtered = work_df[exchange_mask & (tradingsymbol_upper == symbol)]

        if segment:
            segment_mask = exact_filtered["segment"].astype(str).str.upper() == segment
            exact_filtered = exact_filtered[segment_mask]

        if not exact_filtered.empty:
            best_match = self._select_best_match(exact_filtered)
            token_value = best_match["instrument_token"]
            try:
                return int(token_value)
            except (TypeError, ValueError):
                try:
                    return int(float(token_value))
                except (TypeError, ValueError):
                    return None

        partial_filtered = work_df[
            exchange_mask
            & tradingsymbol_upper.str.startswith(symbol, na=False)
        ]
        if segment:
            segment_mask = partial_filtered["segment"].astype(str).str.upper() == segment
            partial_filtered = partial_filtered[segment_mask]

        if partial_filtered.empty:
            partial_filtered = work_df[
                exchange_mask
                & tradingsymbol_upper.str.contains(symbol, na=False, regex=False)
            ]
            if segment:
                segment_mask = partial_filtered["segment"].astype(str).str.upper() == segment
                partial_filtered = partial_filtered[segment_mask]

        if partial_filtered.empty:
            return None

        best_match = self._select_best_match(partial_filtered)
        token_value = best_match["instrument_token"]
        try:
            return int(token_value)
        except (TypeError, ValueError):
            try:
                return int(float(token_value))
            except (TypeError, ValueError):
                return None

    def _select_best_match(self, matches: pd.DataFrame) -> pd.Series:
        if len(matches) == 1:
            return matches.iloc[0]

        candidates = matches.copy()

        preferred_eq = candidates[
            (candidates["segment"].astype(str).str.upper() == "NSE")
            & (candidates["instrument_type"].astype(str).str.upper() == "EQ")
        ]
        if not preferred_eq.empty:
            return preferred_eq.iloc[0]

        derivative_types = {"FUT", "CE", "PE"}
        derivative_matches = candidates[
            candidates["instrument_type"].astype(str).str.upper().isin(derivative_types)
        ].copy()
        if not derivative_matches.empty:
            derivative_matches["expiry"] = pd.to_datetime(
                derivative_matches["expiry"], errors="coerce"
            )
            today_dt = pd.Timestamp(date.today())
            valid_derivatives = derivative_matches[
                derivative_matches["expiry"].notna()
                & (derivative_matches["expiry"] >= today_dt)
            ]
            prioritized = valid_derivatives if not valid_derivatives.empty else derivative_matches
            prioritized = prioritized.sort_values(
                by=["expiry"], ascending=True, na_position="last"
            )
            return prioritized.iloc[0]

        return candidates.iloc[0]

    def _load_csv(self, file_path: Path) -> pd.DataFrame:
        if not file_path.is_file():
            return pd.DataFrame(columns=self._REQUIRED_COLUMNS)

        try:
            df = pd.read_csv(file_path)
        except Exception as exc:
            raise RuntimeError(f"Failed to read instrument file: {file_path}") from exc

        df = self._ensure_required_columns(df)
        return self._normalize_dataframe(df)

    def _load_metadata(self) -> dict[str, Any]:
        if not self._metadata_path.is_file():
            return {}

        try:
            with self._metadata_path.open("r", encoding="utf-8") as file_obj:
                data = json.load(file_obj)
        except Exception as exc:
            raise RuntimeError("Failed to read metadata.json") from exc

        return data if isinstance(data, dict) else {}

    def _save_metadata(self) -> None:
        try:
            with self._metadata_path.open("w", encoding="utf-8") as file_obj:
                json.dump(self._metadata, file_obj, indent=2)
        except Exception as exc:
            raise RuntimeError("Failed to write metadata.json") from exc

    def _ensure_required_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        work_df = df.copy()
        for column in self._REQUIRED_COLUMNS:
            if column not in work_df.columns:
                work_df[column] = pd.NA
        return work_df[self._REQUIRED_COLUMNS]

    def _normalize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        work_df = df.copy()
        work_df["tradingsymbol"] = work_df["tradingsymbol"].astype(str).str.strip().str.upper()
        work_df["name"] = work_df["name"].astype(str).str.strip()
        work_df["exchange"] = work_df["exchange"].astype(str).str.strip().str.upper()
        work_df["segment"] = work_df["segment"].astype(str).str.strip().str.upper()
        work_df["instrument_type"] = (
            work_df["instrument_type"].astype(str).str.strip().str.upper()
        )
        work_df["expiry"] = pd.to_datetime(work_df["expiry"], errors="coerce")

        work_df["instrument_token"] = pd.to_numeric(
            work_df["instrument_token"], errors="coerce"
        )
        work_df["strike"] = pd.to_numeric(work_df["strike"], errors="coerce")
        work_df["lot_size"] = pd.to_numeric(work_df["lot_size"], errors="coerce")

        work_df = work_df.dropna(subset=["instrument_token"])
        work_df["instrument_token"] = work_df["instrument_token"].astype("int64")
        return work_df

    def _deduplicate_archive(self, df: pd.DataFrame) -> pd.DataFrame:
        work_df = df.copy()
        work_df = work_df.drop_duplicates(subset=["instrument_token"], keep="last")

        expiry_key = work_df["expiry"].dt.strftime("%Y-%m-%d").fillna("")
        work_df = work_df.assign(_expiry_key=expiry_key)
        work_df = work_df.drop_duplicates(
            subset=["tradingsymbol", "exchange", "_expiry_key"],
            keep="last",
        )
        work_df = work_df.drop(columns=["_expiry_key"])
        return work_df.reset_index(drop=True)

    def _prepare_combined_df(self) -> pd.DataFrame:
        combined_df = pd.concat(
            [self._latest_df, self._archive_df], ignore_index=True, sort=False
        )
        if combined_df.empty:
            return pd.DataFrame(columns=self._REQUIRED_COLUMNS)

        combined_df = self._ensure_required_columns(combined_df)
        combined_df = self._normalize_dataframe(combined_df)
        combined_df = self._deduplicate_archive(combined_df)
        return combined_df


__all__ = ["InstrumentMapper"]
