import os
import glob
import sys
import re
from datetime import datetime, time, timedelta
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit_shadcn_ui as ui

from navbar import TV_UP, TV_DOWN, PRIMARY_BLUE, BG_COLOR, BORDER_COLOR
from dashboard_page.dashboard_features import talib_indicators

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(PROJECT_ROOT, "Data", "Logs", "Backtesting_result_log")
DATA_DIR = os.path.join(PROJECT_ROOT, "Data", "testing_data", "Data_files")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Backtesting import data_normalizer

_IST_TIMEZONE = "Asia/Kolkata"
_PRICE_REQUIRED_COLUMNS = ["Open", "High", "Low", "Close"]
_MARKET_OPEN = time(9, 15)
_MARKET_CLOSE = time(15, 30)


def _get_files_by_ext(directory, extension):
    return sorted(glob.glob(os.path.join(directory, "**", f"*{extension}"), recursive=True), reverse=True)


def _extract_timestamp_from_filename(filename: str) -> datetime | None:
    stem = os.path.splitext(str(filename))[0]
    compact_match = re.search(r"(\d{8}_\d{6})", stem)
    if compact_match:
        try:
            return datetime.strptime(compact_match.group(1), "%Y%m%d_%H%M%S")
        except ValueError:
            pass

    dense_match = re.search(r"(\d{14})", stem)
    if dense_match:
        try:
            return datetime.strptime(dense_match.group(1), "%Y%m%d%H%M%S")
        except ValueError:
            pass

    mixed_match = re.search(r"(\d{4}-\d{2}-\d{2}[T_ ]\d{2}[-:]\d{2}[-:]\d{2})", stem)
    if mixed_match:
        token = mixed_match.group(1).replace("T", " ").replace("_", " ")
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H-%M-%S"):
            try:
                return datetime.strptime(token, fmt)
            except ValueError:
                continue

    date_only_match = re.search(r"(\d{4}-\d{2}-\d{2})", stem)
    if date_only_match:
        try:
            return datetime.strptime(date_only_match.group(1), "%Y-%m-%d")
        except ValueError:
            pass
    return None


def _build_trade_csv_options(trade_csvs: list[str]) -> dict[str, str]:
    results: list[dict[str, object]] = []

    for path in trade_csvs:
        filename = os.path.basename(path)
        timestamp = _extract_timestamp_from_filename(filename)
        if timestamp is None:
            try:
                timestamp = datetime.fromtimestamp(os.path.getmtime(path))
            except OSError:
                timestamp = datetime.min

        results.append(
            {
                "name": filename,
                "path": path,
                "timestamp": timestamp,
            }
        )

    results = sorted(results, key=lambda x: x["timestamp"], reverse=True)
    if len(results) > 1:
        first_ts = results[0]["timestamp"]
        last_ts = results[-1]["timestamp"]
        if isinstance(first_ts, datetime) and isinstance(last_ts, datetime):
            if first_ts < last_ts:
                print(
                    "[Dashboard] warning: trade results ordering sanity check failed; "
                    "expected latest-first sorting."
                )

    options: dict[str, str] = {}
    for item in results:
        name = str(item["name"])
        # Preserve deterministic ordering while avoiding key collisions.
        if name in options:
            continue
        options[name] = str(item["path"])
    return options


def _validate_trade_toggle(instance_id):
    if st.session_state.get(f"plot_toggle_{instance_id}"):
        trade_sel = st.session_state.get(f"trade_sel_{instance_id}")
        if not trade_sel or trade_sel == "None":
            st.toast("Please select a backtest result for ploting buy/sell indicators!", icon="🚨")
            st.session_state[f"plot_toggle_{instance_id}"] = False


def _prepare_price_dataframe(raw_df: pd.DataFrame) -> pd.DataFrame:
    normalized = data_normalizer.prepare_ohlcv_for_plot(
        raw_df,
        enforce_market_hours=True,
    )
    normalized.index = _to_ist_index(
        normalized.index,
        context_label="price candles",
    )
    normalized = normalized[~normalized.index.isna()]
    normalized = normalized.sort_index()
    normalized = normalized[~normalized.index.duplicated(keep="first")]
    if normalized.empty:
        raise ValueError("No valid OHLCV rows found after preparation")

    missing_ohlc = [column for column in _PRICE_REQUIRED_COLUMNS if column not in normalized.columns]
    if missing_ohlc:
        raise ValueError(f"Missing required OHLC columns for plotting: {missing_ohlc}")
    _assert_market_hours_if_intraday(normalized.index, context_label="price candles")
    return normalized


def _prepare_trades_dataframe(raw_df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(raw_df, pd.DataFrame) or raw_df.empty:
        return pd.DataFrame()

    trades = raw_df.copy()
    if "Entry Date" not in trades.columns:
        raise ValueError("Trade log must include 'Entry Date' column")

    trades["Entry Date"] = pd.to_datetime(trades["Entry Date"], errors="coerce")
    if "Close Date" in trades.columns:
        trades["Close Date"] = pd.to_datetime(trades["Close Date"], errors="coerce")

    trades["Entry Date"] = trades["Entry Date"].map(_to_ist_timestamp)
    if "Close Date" in trades.columns:
        trades["Close Date"] = trades["Close Date"].map(_to_ist_timestamp)

    trades = trades.dropna(subset=["Entry Date"])
    return trades


def _align_single_trade_timestamp(
    ts: object,
    candle_index: pd.DatetimeIndex,
    *,
    interval_delta: pd.Timedelta | None,
) -> pd.Timestamp | None:
    if pd.isna(ts):
        return pd.NaT
    if not isinstance(candle_index, pd.DatetimeIndex) or candle_index.empty:
        return pd.NaT

    ts_value = pd.Timestamp(ts)
    if candle_index.tz is None:
        if ts_value.tzinfo is not None:
            ts_value = ts_value.tz_convert(_IST_TIMEZONE).tz_localize(None)
    elif ts_value.tzinfo is None:
        ts_value = ts_value.tz_localize(candle_index.tz)
    else:
        ts_value = ts_value.tz_convert(candle_index.tz)

    first_candle = candle_index[0]
    last_candle = candle_index[-1]

    if ts_value <= first_candle:
        return first_candle
    if ts_value >= last_candle:
        return last_candle

    if ts_value in candle_index:
        return ts_value

    rounded_ts = ts_value
    if interval_delta is not None and interval_delta > pd.Timedelta(0):
        anchor = first_candle
        elapsed = ts_value - anchor
        ratio = elapsed / interval_delta
        rounded_steps = int(round(float(ratio)))
        rounded_ts = anchor + (rounded_steps * interval_delta)
        if rounded_ts < first_candle:
            rounded_ts = first_candle
        if rounded_ts > last_candle:
            rounded_ts = last_candle

    nearest_pos = candle_index.get_indexer([rounded_ts], method="nearest")
    if len(nearest_pos) == 0 or int(nearest_pos[0]) < 0:
        return pd.NaT
    return candle_index[int(nearest_pos[0])]


def _align_trade_timestamps_to_candles(
    trades: pd.DataFrame,
    candle_index: pd.DatetimeIndex,
) -> pd.DataFrame:
    if trades is None:
        return pd.DataFrame()
    if trades.empty:
        return trades.copy()

    aligned = trades.copy()
    interval_delta = _infer_interval_delta(candle_index)
    before_count = int(len(aligned))
    aligned["Entry Candle"] = [
        _align_single_trade_timestamp(
            ts,
            candle_index,
            interval_delta=interval_delta,
        )
        for ts in aligned["Entry Date"]
    ]
    if "Close Date" in aligned.columns:
        aligned["Close Candle"] = [
            _align_single_trade_timestamp(
                ts,
                candle_index,
                interval_delta=interval_delta,
            )
            for ts in aligned["Close Date"]
        ]

    aligned = aligned.dropna(subset=["Entry Candle"])
    after_count = int(len(aligned))

    entry_unmatched = int((~aligned["Entry Candle"].isin(candle_index)).sum())
    close_unmatched = 0
    if "Close Candle" in aligned.columns:
        close_unmatched = int((~aligned["Close Candle"].isin(candle_index)).sum())

    alignment_mismatch = int((aligned["Entry Candle"] != aligned["Entry Date"]).sum())
    dropped_count = max(before_count - after_count, 0)
    aligned.attrs["alignment_stats"] = {
        "before_count": before_count,
        "after_count": after_count,
        "dropped_count": dropped_count,
        "entry_mismatch_count": alignment_mismatch,
        "entry_unmatched_count": entry_unmatched,
        "close_unmatched_count": close_unmatched,
        "interval_seconds": (
            int(interval_delta.total_seconds()) if interval_delta is not None else None
        ),
    }
    return aligned


def _marker_y_for_timestamps(
    timestamps: pd.Series,
    price_series: pd.Series,
    factor: float,
) -> list[float | None]:
    points: list[float | None] = []
    for ts in timestamps:
        if pd.isna(ts) or ts not in price_series.index:
            points.append(None)
            continue
        value = price_series.at[ts]
        points.append(float(value) * factor if pd.notna(value) else None)
    return points


def _estimate_missing_candle_count(index: pd.DatetimeIndex) -> tuple[int, int]:
    if not isinstance(index, pd.DatetimeIndex) or len(index) < 2:
        return len(index), 0

    diff_series = pd.Series(index).diff().dropna()
    diff_series = diff_series[diff_series > pd.Timedelta(0)]
    if diff_series.empty:
        return len(index), 0

    step = diff_series.mode().iloc[0]
    if pd.isna(step) or step <= pd.Timedelta(0):
        return len(index), 0

    total_expected = 0
    total_missing = 0
    grouped = pd.Series(index).groupby(index.normalize())
    for _, day_values in grouped:
        day_index = pd.DatetimeIndex(day_values).sort_values()
        if day_index.empty:
            continue
        day_expected = pd.date_range(
            start=day_index.min(),
            end=day_index.max(),
            freq=step,
            tz=day_index.tz,
        )
        total_expected += len(day_expected)
        total_missing += len(day_expected.difference(day_index))

    return total_expected, total_missing


def _infer_interval_delta(index: pd.DatetimeIndex) -> pd.Timedelta | None:
    if not isinstance(index, pd.DatetimeIndex) or len(index) < 2:
        return None
    sorted_index = index.sort_values()
    diffs = sorted_index.to_series().diff().dropna()
    diffs = diffs[diffs > pd.Timedelta(0)]
    if diffs.empty:
        return None
    return diffs.mode().iloc[0]


def _to_ist_timestamp(value: object) -> pd.Timestamp:
    if pd.isna(value):
        return pd.NaT
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return pd.NaT
    ts = pd.Timestamp(parsed)
    if ts.tzinfo is None:
        # Naive timestamps are treated as already in IST.
        return ts.tz_localize(_IST_TIMEZONE)
    return ts.tz_convert(_IST_TIMEZONE)


def _to_ist_index(index: pd.Index, *, context_label: str) -> pd.DatetimeIndex:
    parsed_values: list[pd.Timestamp] = []
    timezone_flags: list[bool] = []
    for raw_value in list(index):
        parsed_raw = pd.to_datetime(raw_value, errors="coerce")
        if pd.isna(parsed_raw):
            continue
        raw_timestamp = pd.Timestamp(parsed_raw)
        timezone_flags.append(raw_timestamp.tzinfo is not None)

        ts = _to_ist_timestamp(raw_value)
        if pd.isna(ts):
            continue
        parsed_values.append(pd.Timestamp(ts))

    if not parsed_values:
        return pd.DatetimeIndex([], tz=_IST_TIMEZONE)

    has_aware = any(timezone_flags)
    has_naive = any(not item for item in timezone_flags)
    if has_aware and has_naive:
        raise ValueError(f"Mixed timezone data detected for {context_label}")

    converted = pd.DatetimeIndex(parsed_values)
    if converted.tz is None:
        converted = converted.tz_localize(_IST_TIMEZONE)
    else:
        converted = converted.tz_convert(_IST_TIMEZONE)
    return converted


def _is_intraday_index(index: pd.DatetimeIndex) -> bool:
    if not isinstance(index, pd.DatetimeIndex) or index.empty:
        return False
    unique_times = {
        (ts.hour, ts.minute, ts.second, ts.microsecond)
        for ts in index
    }
    if len(unique_times) == 1 and next(iter(unique_times)) in {(0, 0, 0, 0), (5, 30, 0, 0)}:
        return False
    return True


def _assert_market_hours_if_intraday(
    index: pd.DatetimeIndex,
    *,
    context_label: str,
) -> None:
    if not _is_intraday_index(index):
        return
    invalid_times = [
        ts
        for ts in index
        if not (_MARKET_OPEN <= ts.time() <= _MARKET_CLOSE)
    ]
    if invalid_times:
        sample = ", ".join(str(ts) for ts in invalid_times[:5])
        raise ValueError(
            f"Detected timestamps outside market hours for {context_label}: {sample}"
        )


def _filter_trades_to_visible_range(
    trades: pd.DataFrame,
    candle_index: pd.DatetimeIndex,
) -> tuple[pd.DataFrame, int]:
    if trades is None or trades.empty:
        return pd.DataFrame(), 0
    if not isinstance(candle_index, pd.DatetimeIndex) or candle_index.empty:
        return trades.copy(), 0

    min_candle = candle_index.min()
    max_candle = candle_index.max()
    visible = trades.copy()

    entry_in_range = (
        (visible["Entry Date"] >= min_candle)
        & (visible["Entry Date"] <= max_candle)
    )
    if "Close Date" in visible.columns:
        close_in_range = (
            visible["Close Date"].notna()
            & (visible["Close Date"] >= min_candle)
            & (visible["Close Date"] <= max_candle)
        )
        keep_mask = entry_in_range | close_in_range
    else:
        keep_mask = entry_in_range

    filtered = visible[keep_mask].copy()
    removed = max(int(len(visible) - len(filtered)), 0)
    return filtered, removed


@st.dialog("Complete Raw Console Log", width="large")
def _render_log_modal(log_text):
    with st.container(height=600):
        st.code(log_text if log_text else "System IDLE: No logs detected based on current filter.", language="text")


def _render_dashboard_instance(instance_id, price_csv_options, trade_csv_options):
    st.markdown(f"#### ⚛️ Strategy Environment [ID: {instance_id}]")

    # Control Panel
    st.markdown("<div class='card-container'>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns([1.5, 1.5, 2, 0.8], gap="medium")

    with c1:
        selected_price_name = st.selectbox("Symbol Pricing Data", options=["None"] + list(price_csv_options.keys()), key=f"price_sel_{instance_id}")
    with c2:
        selected_trade_name = st.selectbox("Backtest Strategy Result", options=["None"] + list(trade_csv_options.keys()), key=f"trade_sel_{instance_id}")

    # Load Main Pricing Database
    df_price = None
    if selected_price_name != "None":
        try:
            raw_price_df = pd.read_csv(price_csv_options[selected_price_name])
            df_price = _prepare_price_dataframe(raw_price_df)
        except Exception as e:
            st.error(f"Failed to load price data: {str(e)}")

    # Calculate supported Indicators dynamically
    can_load = talib_indicators.get_loadable_indicators(df_price)

    with c3:
        if can_load:
            selected_indicators = st.multiselect("Overlay Indicators", options=sorted(can_load), key=f"overlay_sel_{instance_id}")
        else:
            st.multiselect("Overlay Indicators", options=[], disabled=True, key=f"overlay_sel_none_{instance_id}")
            selected_indicators = []

    with c4:
        st.markdown("<br>", unsafe_allow_html=True)
        if ui.button("Sync Instance", key=f"sync_btn_{instance_id}"):
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    # Load Trades & Logs
    df_trades = None
    log_content = ""
    if selected_trade_name != "None":
        try:
            raw_trades_df = pd.read_csv(trade_csv_options[selected_trade_name])
            df_trades = _prepare_trades_dataframe(raw_trades_df)

            expected_log_name = selected_trade_name.replace("_result_", "_log_").replace(".csv", ".log")
            expected_log_path = os.path.join(LOG_DIR, expected_log_name)
            if os.path.exists(expected_log_path):
                with open(expected_log_path, "r", encoding="utf-8") as f:
                    log_content = f.read()
        except Exception as e:
            st.error(f"Failed to load trades data: {str(e)}")

    # KPI Section
    if df_trades is not None and not df_trades.empty:
        target_pnl_col = "Gross P&L" if "Gross P&L" in df_trades.columns else "Net P&L" if "Net P&L" in df_trades.columns else None

        if target_pnl_col:
            total_pnl = df_trades[target_pnl_col].sum()
            total_trades = len(df_trades)
            win_count = len(df_trades[df_trades[target_pnl_col] > 0])
            win_rate = (win_count / total_trades) * 100 if total_trades > 0 else 0
            avg_pnl = total_pnl / total_trades if total_trades > 0 else 0

            pnl_class = "profit" if total_pnl >= 0 else "loss"
            avg_class = "profit" if avg_pnl >= 0 else "loss"

            st.markdown(f"""
            <div style='display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 5px;'>
                <div class='kpi-card'><div class='kpi-title'>Total Trades Evaluated</div><div class='kpi-value'>{total_trades}</div></div>
                <div class='kpi-card'><div class='kpi-title'>Strategy Win Rate</div><div class='kpi-value'>{win_rate:.1f}%</div></div>
                <div class='kpi-card'><div class='kpi-title'>Total Captured P&L</div><div class='kpi-value {pnl_class}'>₹{total_pnl:,.2f}</div></div>
                <div class='kpi-card'><div class='kpi-title'>Average Trade Yield</div><div class='kpi-value {avg_class}'>₹{avg_pnl:,.2f}</div></div>
            </div>
            """, unsafe_allow_html=True)

    # Parse active indicators into overlays vs oscillators
    overlays, oscillators = talib_indicators.split_indicators(selected_indicators)

    ui_grid_height = 600 + (len(oscillators) * 150)

    # Main Content Split
    main_col_left, main_col_right = st.columns([7, 3], gap="medium")

    # LEFT PANE: Chart & Log Modal
    with main_col_left:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)

        chart_head_c1, chart_head_c2 = st.columns([7, 3])
        plot_markers = chart_head_c2.toggle("💡 Plot Buy/Sell Actions", key=f"plot_toggle_{instance_id}", on_change=_validate_trade_toggle, args=(instance_id,))

        if df_price is not None and not df_price.empty:
            df_price = df_price.copy()
            df_price.index = pd.to_datetime(df_price.index, errors="coerce")
            df_price = df_price[~df_price.index.isna()]
            df_price = df_price.sort_index()
            df_price = df_price[~df_price.index.duplicated(keep="first")]

            if df_price.empty:
                st.error("No valid candle timestamps are available for plotting.")
                st.markdown("</div>", unsafe_allow_html=True)
                return

            missing_ohlc = [column for column in _PRICE_REQUIRED_COLUMNS if column not in df_price.columns]
            if missing_ohlc:
                st.error(f"Cannot render chart. Missing OHLC columns: {missing_ohlc}")
                st.markdown("</div>", unsafe_allow_html=True)
                return

            df_price_sub = df_price.tail(800)
            expected_count, missing_count = _estimate_missing_candle_count(df_price_sub.index)
            st.caption(
                f"Candles: {len(df_price_sub)} | Expected: {expected_count} | Missing: {missing_count}"
            )

            num_rows = 2 + len(oscillators)
            row_heights = [0.65, 0.15]
            if oscillators:
                row_heights.extend([0.20 / len(oscillators)] * len(oscillators))

            fig = make_subplots(rows=num_rows, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=row_heights)
            GRID_COLOR = 'rgba(0,0,0,0.05)'

            fig.add_trace(go.Candlestick(
                x=df_price_sub.index, open=df_price_sub["Open"], high=df_price_sub["High"],
                low=df_price_sub["Low"], close=df_price_sub["Close"],
                name="Price", increasing_line_color=TV_UP, increasing_fillcolor=TV_UP,
                decreasing_line_color=TV_DOWN, decreasing_fillcolor=TV_DOWN, text=df_price_sub.index,
            ), row=1, col=1)

            hover_template = "Open: %{open:.2f}<br>High: %{high:.2f}<br>Low: %{low:.2f}<br>Close: %{close:.2f}<extra></extra>"
            fig.update_traces(line_width=1, selector=dict(type='candlestick'), hovertemplate=hover_template)

            if "Volume" in df_price_sub.columns:
                vol_colors = [TV_UP if c >= o else TV_DOWN for o, c in zip(df_price_sub["Open"], df_price_sub["Close"])]
                fig.add_trace(go.Bar(x=df_price_sub.index, y=df_price_sub["Volume"], marker_color=vol_colors, opacity=0.8, name="Vol", hoverinfo="none"), row=2, col=1)

            inputs = talib_indicators.build_talib_inputs(df_price_sub)
            IND_COLORS = [PRIMARY_BLUE, "#f5c542", "#9C27B0", "#FF9800", "#E91E63", "#00BCD4"]

            def plot_ind(ind_name, func, rw, c_idx):
                out = talib_indicators.run_indicator(func, inputs)
                if out is None:
                    return

                colr = IND_COLORS[c_idx % len(IND_COLORS)]
                if isinstance(out, (list, tuple)):
                    for idx, out_s in enumerate(out):
                        fig.add_trace(go.Scattergl(x=df_price_sub.index, y=out_s, mode='lines', line=dict(width=1.2, color=IND_COLORS[(c_idx + idx) % len(IND_COLORS)]), name=f"{ind_name} [{idx}]"), row=rw, col=1)
                else:
                    fig.add_trace(go.Scattergl(x=df_price_sub.index, y=out, mode='lines', line=dict(width=1.2, color=colr), name=ind_name), row=rw, col=1)

            for i, (ind, func) in enumerate(overlays):
                plot_ind(ind, func, 1, i)

            current_rw = 3
            for i, (ind, func) in enumerate(oscillators):
                plot_ind(ind, func, current_rw, i + 8)
                fig.update_yaxes(title_text=ind, row=current_rw, col=1, title_font=dict(size=10, color="gray"))
                current_rw += 1

            if plot_markers and df_trades is not None and "Entry Date" in df_trades.columns:
                visible_trades, removed_out_of_range = _filter_trades_to_visible_range(
                    df_trades,
                    df_price_sub.index,
                )
                aligned_trades = _align_trade_timestamps_to_candles(
                    visible_trades,
                    df_price_sub.index,
                )
                alignment_stats = aligned_trades.attrs.get("alignment_stats", {})
                before_count = int(alignment_stats.get("before_count", len(visible_trades)))
                after_count = int(alignment_stats.get("after_count", len(aligned_trades)))
                dropped_count = int(alignment_stats.get("dropped_count", 0))
                entry_mismatch = int(alignment_stats.get("entry_mismatch_count", 0))
                unmatched_signals = int(alignment_stats.get("entry_unmatched_count", 0)) + int(
                    alignment_stats.get("close_unmatched_count", 0)
                )
                dt_min, dt_max = df_price_sub.index.min(), df_price_sub.index.max()
                sub_trades = aligned_trades.copy()

                if not sub_trades.empty:
                    assert sub_trades["Entry Candle"].min() >= dt_min
                    assert sub_trades["Entry Candle"].max() <= dt_max

                st.caption(
                    "Aligned trades (nearest candle): "
                    f"before={before_count}, after={after_count}, "
                    f"dropped={dropped_count}, outside-range-removed={removed_out_of_range}, "
                    f"entry-mismatched={entry_mismatch}"
                )
                if dropped_count > 0:
                    st.warning(f"{dropped_count} trades were dropped during timestamp alignment.")
                if unmatched_signals > 0:
                    st.warning(f"{unmatched_signals} signal timestamps did not map to candles.")

                # Marker timestamps are aligned to real candle timestamps.

                longs = sub_trades[sub_trades["Direction"] == "BUY"]
                if not longs.empty:
                    # Only plot entry marker if aligned entry candle is within visible range.
                    longs_en = longs[
                        (longs["Entry Candle"] >= dt_min) & (longs["Entry Candle"] <= dt_max)
                    ]
                    if not longs_en.empty:
                        fig.add_trace(go.Scattergl(
                            x=longs_en["Entry Candle"],
                            y=_marker_y_for_timestamps(longs_en["Entry Candle"], df_price_sub["Low"], 0.985),
                            mode='markers', name='Long Entry (Buy)',
                            marker=dict(symbol='triangle-up', size=14, color=TV_UP, line=dict(width=1, color='white'))
                        ), row=1, col=1)
                    # Only plot exit marker if aligned close candle is within visible range.
                    if "Close Candle" in longs.columns:
                        longs_ex = longs[
                            (longs["Close Candle"] >= dt_min) & (longs["Close Candle"] <= dt_max)
                        ]
                        if not longs_ex.empty:
                            fig.add_trace(go.Scattergl(
                                x=longs_ex["Close Candle"],
                                y=_marker_y_for_timestamps(longs_ex["Close Candle"], df_price_sub["High"], 1.015),
                                mode='markers', name='Long Exit (Sell)',
                                marker=dict(symbol='triangle-down', size=12, color='#FF9800', line=dict(width=1, color='white'))
                            ), row=1, col=1)

                shorts = sub_trades[sub_trades["Direction"] == "SELL"]
                if not shorts.empty:
                    shorts_en = shorts[
                        (shorts["Entry Candle"] >= dt_min) & (shorts["Entry Candle"] <= dt_max)
                    ]
                    if not shorts_en.empty:
                        fig.add_trace(go.Scattergl(
                            x=shorts_en["Entry Candle"],
                            y=_marker_y_for_timestamps(shorts_en["Entry Candle"], df_price_sub["High"], 1.015),
                            mode='markers', name='Short Entry (Sell)',
                            marker=dict(symbol='triangle-down', size=14, color=TV_DOWN, line=dict(width=1, color='white'))
                        ), row=1, col=1)
                    if "Close Candle" in shorts.columns:
                        shorts_ex = shorts[
                            (shorts["Close Candle"] >= dt_min) & (shorts["Close Candle"] <= dt_max)
                        ]
                        if not shorts_ex.empty:
                            fig.add_trace(go.Scattergl(
                                x=shorts_ex["Close Candle"],
                                y=_marker_y_for_timestamps(shorts_ex["Close Candle"], df_price_sub["Low"], 0.985),
                                mode='markers', name='Short Exit (Cover)',
                                marker=dict(symbol='triangle-up', size=12, color='#FF9800', line=dict(width=1, color='white'))
                            ), row=1, col=1)

                unmatched_entry = int((~sub_trades["Entry Candle"].isin(df_price_sub.index)).sum())
                unmatched_close = 0
                if "Close Candle" in sub_trades.columns:
                    unmatched_close = int((~sub_trades["Close Candle"].isin(df_price_sub.index)).sum())
                total_unmatched = unmatched_entry + unmatched_close
                st.caption(f"Unmatched signal timestamps: {total_unmatched}")
                if total_unmatched == 0:
                    assert sub_trades["Entry Candle"].isin(df_price_sub.index).all()
                    if "Close Candle" in sub_trades.columns:
                        assert sub_trades["Close Candle"].isin(df_price_sub.index).all()
                else:
                    st.warning(
                        "Signal/candle alignment sanity warning: some signal timestamps "
                        "are not present in plotted candle index."
                    )

            fig.update_layout(
                height=ui_grid_height, plot_bgcolor=BG_COLOR, paper_bgcolor=BG_COLOR,
                xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10),
                hovermode="x unified", dragmode="pan", font=dict(family="Inter", size=12, color="#000000"),
                legend=dict(orientation="h", yanchor="bottom", y=1.00, xanchor="right", x=1),
                uirevision="stable"
            )
            fig.update_xaxes(showgrid=True, gridcolor=GRID_COLOR, showline=False, zeroline=False, showspikes=True, spikemode="across", spikecolor="grey", spikethickness=1)
            fig.update_yaxes(showgrid=True, gridcolor=GRID_COLOR, showline=False, zeroline=False, showspikes=True, spikemode="across", spikecolor="grey", spikethickness=1, tickformat=".2f")
            for r in range(1, num_rows):
                fig.update_xaxes(showticklabels=False, row=r, col=1)

            st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True, "displayModeBar": False}, key=f"plotly_chart_{instance_id}")
        else:
            st.info("No Symbol Pricing Data selected for this instance.")
        st.markdown("</div>", unsafe_allow_html=True)

        # Log Modal
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        c_log_head, c_log_btn = st.columns([5, 1])
        c_log_head.markdown("<h5 style='margin-bottom:0;'>Terminal Execution Block</h5>", unsafe_allow_html=True)

        if c_log_btn.button("🔍 Expand Full Log", use_container_width=True, key=f"log_btn_{instance_id}"):
            _render_log_modal(log_content)

        if log_content:
            preview_block = "\n".join(log_content.split("\n")[-15:])
            st.code(preview_block, language="text")
        else:
            st.caption("Awaiting signal generation...")
        st.markdown("</div>", unsafe_allow_html=True)

    # RIGHT PANE: Trade Book
    with main_col_right:
        st.markdown("<div class='card-container'>", unsafe_allow_html=True)
        st.markdown("<h5>Trade Book</h5>", unsafe_allow_html=True)

        if df_trades is not None and not df_trades.empty:
            def color_pnl(val):
                try:
                    if pd.isna(val): return ''
                    v = float(str(val).replace(',', '').replace('+', ''))
                    if v > 0: return f'color: {TV_UP}; font-weight: bold; background-color: rgba(8,153,129,0.05)'
                    elif v < 0: return f'color: {TV_DOWN}; font-weight: bold; background-color: rgba(242,54,69,0.05)'
                except Exception: pass
                return ''

            styled_df = df_trades.style
            if "Gross P&L" in df_trades.columns:
                styled_df = styled_df.map(color_pnl, subset=["Gross P&L"])
            if "Net P&L" in df_trades.columns:
                styled_df = styled_df.map(color_pnl, subset=["Net P&L"])

            st.dataframe(styled_df, use_container_width=True, height=ui_grid_height + 150, hide_index=True)
        else:
            st.info("No Backtest Strategy Result selected.")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")


def render() -> None:
    price_csvs = _get_files_by_ext(DATA_DIR, ".csv")
    trade_csvs = _get_files_by_ext(LOG_DIR, ".csv")
    price_csv_options = {os.path.basename(f): f for f in price_csvs}
    trade_csv_options = _build_trade_csv_options(trade_csvs)

    if "dashboard_count" not in st.session_state:
        st.session_state.dashboard_count = 1

    for i in range(1, st.session_state.dashboard_count + 1):
        _render_dashboard_instance(i, price_csv_options, trade_csv_options)

    st.markdown("<br>", unsafe_allow_html=True)
    bot_c1, bot_c2, bot_c3 = st.columns([1, 2, 1])
    if bot_c2.button("➕ Add Another Result Comparator Module", use_container_width=True):
        st.session_state.dashboard_count += 1
        st.rerun()
