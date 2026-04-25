import os
import glob
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


def _get_files_by_ext(directory, extension):
    return sorted(glob.glob(os.path.join(directory, "**", f"*{extension}"), recursive=True), reverse=True)


def _validate_trade_toggle(instance_id):
    if st.session_state.get(f"plot_toggle_{instance_id}"):
        trade_sel = st.session_state.get(f"trade_sel_{instance_id}")
        if not trade_sel or trade_sel == "None":
            st.toast("Please select a backtest result for ploting buy/sell indicators!", icon="🚨")
            st.session_state[f"plot_toggle_{instance_id}"] = False


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
            df_price = pd.read_csv(price_csv_options[selected_price_name])
            date_col = "Date" if "Date" in df_price.columns else "TRADE_DATE"
            if date_col in df_price.columns:
                df_price["Date"] = pd.to_datetime(df_price[date_col])
                df_price.set_index("Date", inplace=True)
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
            df_trades = pd.read_csv(trade_csv_options[selected_trade_name])
            if "Entry Date" in df_trades.columns:
                df_trades["Entry Date"] = pd.to_datetime(df_trades["Entry Date"])

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
            df_price_sub = df_price.tail(800)

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
                if "Close Date" in df_trades.columns and not pd.api.types.is_datetime64_any_dtype(df_trades["Close Date"]):
                    df_trades["Close Date"] = pd.to_datetime(df_trades["Close Date"])

                dt_min, dt_max = df_price_sub.index.min(), df_price_sub.index.max()

                if "Close Date" in df_trades.columns:
                    sub_trades = df_trades[
                        ((df_trades["Entry Date"] >= dt_min) & (df_trades["Entry Date"] <= dt_max)) |
                        ((df_trades["Close Date"] >= dt_min) & (df_trades["Close Date"] <= dt_max))
                    ]
                else:
                    sub_trades = df_trades[(df_trades["Entry Date"] >= dt_min) & (df_trades["Entry Date"] <= dt_max)]

                # Sorted, date-normalized OHLC series — asof() handles weekends/holidays
                price_snap = df_price_sub.copy()
                price_snap.index = price_snap.index.normalize()
                price_snap = price_snap.sort_index()

                def snap_y(dates, col, factor):
                    s = price_snap[col]
                    result = []
                    for d in pd.DatetimeIndex(dates).normalize():
                        val = s.asof(d)
                        result.append(float(val) * factor if pd.notna(val) else None)
                    return result

                longs = sub_trades[sub_trades["Direction"] == "BUY"]
                if not longs.empty:
                    # Only plot entry marker if entry date is within visible range
                    longs_en = longs[(longs["Entry Date"] >= dt_min) & (longs["Entry Date"] <= dt_max)]
                    if not longs_en.empty:
                        fig.add_trace(go.Scattergl(
                            x=longs_en["Entry Date"], y=snap_y(longs_en["Entry Date"], "Low", 0.985),
                            mode='markers', name='Long Entry (Buy)',
                            marker=dict(symbol='triangle-up', size=14, color=TV_UP, line=dict(width=1, color='white'))
                        ), row=1, col=1)
                    # Only plot exit marker if exit date is within visible range
                    if "Close Date" in longs.columns:
                        longs_ex = longs[(longs["Close Date"] >= dt_min) & (longs["Close Date"] <= dt_max)]
                        if not longs_ex.empty:
                            fig.add_trace(go.Scattergl(
                                x=longs_ex["Close Date"], y=snap_y(longs_ex["Close Date"], "High", 1.015),
                                mode='markers', name='Long Exit (Sell)',
                                marker=dict(symbol='triangle-down', size=12, color='#FF9800', line=dict(width=1, color='white'))
                            ), row=1, col=1)

                shorts = sub_trades[sub_trades["Direction"] == "SELL"]
                if not shorts.empty:
                    shorts_en = shorts[(shorts["Entry Date"] >= dt_min) & (shorts["Entry Date"] <= dt_max)]
                    if not shorts_en.empty:
                        fig.add_trace(go.Scattergl(
                            x=shorts_en["Entry Date"], y=snap_y(shorts_en["Entry Date"], "High", 1.015),
                            mode='markers', name='Short Entry (Sell)',
                            marker=dict(symbol='triangle-down', size=14, color=TV_DOWN, line=dict(width=1, color='white'))
                        ), row=1, col=1)
                    if "Close Date" in shorts.columns:
                        shorts_ex = shorts[(shorts["Close Date"] >= dt_min) & (shorts["Close Date"] <= dt_max)]
                        if not shorts_ex.empty:
                            fig.add_trace(go.Scattergl(
                                x=shorts_ex["Close Date"], y=snap_y(shorts_ex["Close Date"], "Low", 0.985),
                                mode='markers', name='Short Exit (Cover)',
                                marker=dict(symbol='triangle-up', size=12, color='#FF9800', line=dict(width=1, color='white'))
                            ), row=1, col=1)

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
    trade_csv_options = {os.path.basename(f): f for f in trade_csvs}

    if "dashboard_count" not in st.session_state:
        st.session_state.dashboard_count = 1

    for i in range(1, st.session_state.dashboard_count + 1):
        _render_dashboard_instance(i, price_csv_options, trade_csv_options)

    st.markdown("<br>", unsafe_allow_html=True)
    bot_c1, bot_c2, bot_c3 = st.columns([1, 2, 1])
    if bot_c2.button("➕ Add Another Result Comparator Module", use_container_width=True):
        st.session_state.dashboard_count += 1
        st.rerun()
