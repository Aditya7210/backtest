import { useEffect, useMemo, useRef, useState } from 'react';
import LightweightCandlestickChart from '../components/LightweightCandlestickChart';
import LightweightLineChart, { type LinePoint } from '../components/LightweightLineChart';
import SearchableDropdown, { type SearchableOption } from '../components/SearchableDropdown';
import { computeIndicators, getBacktest, getBacktests, getCatalog, getHistoricalBars, getIndicators } from '../services/api';
import type { BacktestResult, CatalogEntry, OrderEvent, Trade } from '../types/backtest';
import type { IndicatorMetadata, IndicatorSelection, IndicatorSeries } from '../types/indicators';
import type { OHLCVBar } from '../types/market';

interface PriceOption extends SearchableOption {
  instrument_token: number;
  tradingsymbol: string;
  timeframe: string;
  date_from: string;
  date_to: string;
  total_bars: number;
  data_source: string;
}

interface ResultOption extends SearchableOption {
  task_id: string;
}

interface MarkerDiagnostics {
  totalTrades: number;
  rawMarkers: number;
  collapsedMarkers: number;
  markersPlotted: number;
  outsideVisibleRange: number;
  unmatchedTimestamps: number;
}

interface DashboardModuleState {
  id: number;
  priceId: string;
  tradeTaskId: string;
  selectedIndicators: IndicatorSelection[];
  plotSignals: boolean;
  syncNonce: number;
  chartRangeMode: 'full_result' | 'last_1400' | 'last_5d' | 'last_20d';
  tradebookMode: 'closed_trades' | 'order_events';
}

interface DashboardKpis {
  startingValue: number | null;
  finalValue: number | null;
  netPnl: number | null;
  returnPct: number | null;
  totalTrades: number | null;
  winRate: number | null;
  maxDrawdown: number | null;
  sharpeRatio: number | null;
  profitFactor: number | null;
}

const MAX_VISIBLE_CANDLES = 1400;

function asObj(v: unknown): Record<string, unknown> {
  return v && typeof v === 'object' ? (v as Record<string, unknown>) : {};
}

function asNum(v: unknown): number | null {
  if (typeof v === 'number' && Number.isFinite(v)) return v;
  if (typeof v === 'string') {
    const parsed = Number(v);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function pickFirstNumber(source: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    if (!(key in source)) continue;
    const value = asNum(source[key]);
    if (value != null) return value;
  }
  return null;
}

function pickFirstText(source: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return '';
}

function normalizeDirection(value: unknown): string {
  const raw = String(value ?? '').trim().toUpperCase();
  if (raw === 'LONG' || raw === 'BUY') return 'LONG';
  if (raw === 'SHORT' || raw === 'SELL') return 'SHORT';
  if (raw.includes('SHORT')) return 'SHORT';
  if (raw.includes('LONG')) return 'LONG';
  if (raw.includes('SELL')) return 'SHORT';
  if (raw.includes('BUY')) return 'LONG';
  return raw || 'LONG';
}

function normalizeResultTrades(resultLike: unknown): Trade[] {
  const root = asObj(resultLike);
  const nestedResult = asObj(root.result);
  const candidates: unknown[] = [
    root.trades,
    root.trade_log,
    root.orders,
    root.transactions,
    nestedResult.trades,
    nestedResult.trade_log,
    nestedResult.orders,
    nestedResult.transactions,
  ];
  const source = candidates.find((rows) => Array.isArray(rows));
  if (!Array.isArray(source)) return [];

  const normalized: Trade[] = [];
  for (const row of source) {
    const obj = asObj(row);
    const entry_date = pickFirstText(obj, ['entry_date', 'Entry Date', 'entryDate', 'open_time', 'entry_time', 'timestamp']);
    const exit_date = pickFirstText(obj, ['exit_date', 'Close Date', 'Exit Date', 'exitDate', 'close_time', 'exit_time']);
    const direction = normalizeDirection(
      pickFirstText(obj, ['direction', 'Direction', 'side', 'type']) || obj.direction || obj.Direction,
    );
    const entry_action = pickFirstText(obj, ['entry_action', 'Entry Action']) || (direction === 'SHORT' ? 'SELL_SHORT' : 'BUY');
    const exit_action = pickFirstText(obj, ['exit_action', 'Exit Action']) || (direction === 'SHORT' ? 'BUY_COVER' : 'SELL_EXIT');
    const entry_price = pickFirstNumber(obj, ['entry_price', 'Entry Price', 'entryPrice', 'price', 'buy_price']) ?? 0;
    const exit_price = pickFirstNumber(obj, ['exit_price', 'Exit Price', 'close_price', 'sell_price']) ?? 0;
    const pnl = pickFirstNumber(obj, ['pnl', 'Net P&L', 'net_pnl', 'profit', 'Gross P&L']) ?? 0;
    const size = pickFirstNumber(obj, ['size', 'Qty', 'qty', 'quantity', 'volume']) ?? 0;
    if (!entry_date && !exit_date) continue;
    normalized.push({
      trade_id: pickFirstText(obj, ['trade_id', 'id']) || undefined,
      instrument_token: pickFirstNumber(obj, ['instrument_token']) ?? undefined,
      symbol: pickFirstText(obj, ['symbol', 'Symbol']) || undefined,
      entry_date,
      exit_date,
      direction,
      entry_action,
      exit_action,
      entry_price,
      exit_price,
      pnl,
      net_pnl: pickFirstNumber(obj, ['net_pnl', 'Net P&L', 'pnl']) ?? pnl,
      gross_pnl: pickFirstNumber(obj, ['gross_pnl', 'Gross P&L']) ?? undefined,
      commission: pickFirstNumber(obj, ['commission']) ?? undefined,
      size,
      quantity: pickFirstNumber(obj, ['quantity', 'Qty', 'qty']) ?? undefined,
      bars_held: pickFirstNumber(obj, ['bars_held']) ?? undefined,
      status: pickFirstText(obj, ['status']) || undefined,
      position_before_entry: pickFirstNumber(obj, ['position_before_entry']) ?? undefined,
      position_after_entry: pickFirstNumber(obj, ['position_after_entry']) ?? undefined,
      position_before_exit: pickFirstNumber(obj, ['position_before_exit']) ?? undefined,
      position_after_exit: pickFirstNumber(obj, ['position_after_exit']) ?? undefined,
    });
  }
  return normalized;
}

function normalizeOrderEvents(resultLike: unknown): OrderEvent[] {
  const root = asObj(resultLike);
  const nestedResult = asObj(root.result);
  const source = [root.order_events, nestedResult.order_events, root.trade_events, nestedResult.trade_events]
    .find((rows) => Array.isArray(rows));
  if (!Array.isArray(source)) return [];
  const normalized: OrderEvent[] = [];
  for (const row of source) {
    const obj = asObj(row);
    const time = pickFirstText(obj, ['time', 'timestamp', 'event_time']);
    const action = pickFirstText(obj, ['action', 'type']);
    const status = pickFirstText(obj, ['status']);
    if (!time && !action) continue;
    normalized.push({
      event_id: pickFirstText(obj, ['event_id', 'id']) || undefined,
      time: time || '-',
      action: action || 'UNKNOWN',
      status: status || 'UNKNOWN',
      requested_size: pickFirstNumber(obj, ['requested_size']) ?? undefined,
      executed_size: pickFirstNumber(obj, ['executed_size']) ?? undefined,
      price: pickFirstNumber(obj, ['price']) ?? undefined,
      reason: pickFirstText(obj, ['reason']) || undefined,
      position_before: pickFirstNumber(obj, ['position_before']) ?? undefined,
      position_after: pickFirstNumber(obj, ['position_after']) ?? undefined,
      cash_before: pickFirstNumber(obj, ['cash_before']) ?? undefined,
      cash_after: pickFirstNumber(obj, ['cash_after']) ?? undefined,
    });
  }
  return normalized;
}

function normalizeResultKpis(resultLike: unknown, trades: Trade[]): DashboardKpis {
  const root = asObj(resultLike);
  const metrics = asObj(root.metrics);
  const summary = asObj(root.summary);
  const performance = asObj(root.performance);
  const analyzers = asObj(root.analyzers);
  const nestedResult = asObj(root.result);
  const nestedMetrics = asObj(nestedResult.metrics);
  const nestedSummary = asObj(nestedResult.summary);
  const tradeStats = asObj(metrics.trade_stats);
  const tradeStatsTotal = asObj(asObj(tradeStats.total));
  const tradeStatsWon = asObj(asObj(tradeStats.won));
  const drawdownAnalyzer = asObj(analyzers.drawdown);
  const sharpeAnalyzer = asObj(analyzers.sharpe);
  const config = asObj(root.config);

  const merged = {
    ...nestedSummary,
    ...nestedMetrics,
    ...summary,
    ...performance,
    ...metrics,
    ...root,
  };

  const startingValue =
    pickFirstNumber(merged, ['starting_value', 'start_value', 'initial_capital', 'starting_capital'])
    ?? asNum(config.initial_capital);
  const finalValue =
    pickFirstNumber(merged, ['final_value', 'ending_value', 'final_portfolio_value'])
    ?? asNum(root.final_value);
  const totalTrades =
    pickFirstNumber(merged, ['total_trades', 'trade_count'])
    ?? asNum(tradeStatsTotal.total)
    ?? trades.length;
  const winningTrades =
    pickFirstNumber(merged, ['winning_trades', 'wins'])
    ?? asNum(tradeStatsWon.total)
    ?? trades.filter((t) => t.pnl > 0).length;
  const winRate =
    pickFirstNumber(merged, ['win_rate', 'win_rate_pct'])
    ?? (totalTrades && totalTrades > 0 ? (winningTrades / totalTrades) * 100 : null);
  const maxDrawdown =
    pickFirstNumber(merged, ['max_drawdown', 'max_drawdown_pct', 'drawdown'])
    ?? pickFirstNumber(drawdownAnalyzer, ['max_drawdown', 'drawdown', 'max'])
    ?? pickFirstNumber(asObj(drawdownAnalyzer.max), ['drawdown']);
  const sharpeRatio =
    pickFirstNumber(merged, ['sharpe_ratio', 'sharpe'])
    ?? pickFirstNumber(sharpeAnalyzer, ['sharpe', 'ratio']);
  const profitFactor =
    pickFirstNumber(merged, ['profit_factor'])
    ?? (() => {
      const gp = pickFirstNumber(merged, ['gross_profit', 'gross_pnl_positive']);
      const gl = pickFirstNumber(merged, ['gross_loss', 'gross_pnl_negative']);
      if (gp == null || gl == null || gl === 0) return null;
      return Math.abs(gp / gl);
    })();

  const netPnl =
    pickFirstNumber(merged, ['net_pnl', 'net_profit'])
    ?? (startingValue != null && finalValue != null ? finalValue - startingValue : null);
  const returnPct =
    pickFirstNumber(merged, ['return_pct', 'returns_pct', 'return_percentage'])
    ?? (startingValue != null && finalValue != null && startingValue !== 0
      ? ((finalValue - startingValue) / startingValue) * 100
      : null);

  return {
    startingValue,
    finalValue,
    netPnl,
    returnPct,
    totalTrades,
    winRate,
    maxDrawdown,
    sharpeRatio,
    profitFactor,
  };
}

function formatMetricValue(value: number | null, kind: 'currency' | 'percent' | 'number' | 'ratio'): string {
  if (value == null || !Number.isFinite(value)) return 'N/A';
  if (kind === 'currency') return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 }).format(value);
  if (kind === 'percent') return `${value.toFixed(2)}%`;
  if (kind === 'ratio') return value.toFixed(2);
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(value);
}

function toUnixSeconds(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return Math.floor(value);
  if (typeof value !== 'string') return null;
  const millis = Date.parse(value);
  return Number.isFinite(millis) ? Math.floor(millis / 1000) : null;
}

function parseBars(rawBars: unknown): OHLCVBar[] {
  if (!Array.isArray(rawBars)) return [];
  const parsed: OHLCVBar[] = [];
  for (const row of rawBars) {
    const rec = asObj(row);
    const time = asNum(rec.time) ?? toUnixSeconds(rec.timestamp);
    const open = asNum(rec.open);
    const high = asNum(rec.high);
    const low = asNum(rec.low);
    const close = asNum(rec.close);
    const volume = asNum(rec.volume) ?? 0;
    if (time == null || open == null || high == null || low == null || close == null) continue;
    parsed.push({ time, open, high, low, close, volume });
  }
  parsed.sort((a, b) => a.time - b.time);
  const deduped: OHLCVBar[] = [];
  let lastTime = -1;
  for (const bar of parsed) {
    if (bar.time === lastTime) deduped[deduped.length - 1] = bar;
    else {
      deduped.push(bar);
      lastTime = bar.time;
    }
  }
  return deduped;
}

function normalizeTradeTimestampToUnix(input: string | null | undefined): number | null {
  const raw = (input || '').trim();
  if (!raw) return null;
  const hasTz = /([zZ]|[+-]\d{2}:\d{2})$/.test(raw);
  const normalized = hasTz ? raw : `${raw.replace(' ', 'T')}+05:30`;
  const millis = Date.parse(normalized);
  if (!Number.isFinite(millis)) return null;
  return Math.floor(millis / 1000);
}

function nearestCandleTime(targetUnix: number, candleTimes: number[], toleranceSeconds: number): number | null {
  if (!candleTimes.length) return null;
  let best = candleTimes[0];
  let diff = Math.abs(best - targetUnix);
  for (let i = 1; i < candleTimes.length; i += 1) {
    const d = Math.abs(candleTimes[i] - targetUnix);
    if (d < diff) {
      diff = d;
      best = candleTimes[i];
    }
  }
  if (diff > toleranceSeconds) return null;
  return best;
}

function directionKind(direction: string): 'long' | 'short' | 'unknown' {
  const d = (direction || '').toUpperCase();
  if (d === 'BUY' || d === 'LONG') return 'long';
  if (d === 'SELL' || d === 'SHORT') return 'short';
  if (d.includes('LONG')) return 'long';
  if (d.includes('SHORT') || d.includes('SELL')) return 'short';
  return 'unknown';
}

function timeframeToleranceSeconds(timeframe: string | undefined): number {
  const normalized = String(timeframe || '').toLowerCase();
  if (normalized === '1min' || normalized === 'minute') return 60;
  if (normalized === '3min' || normalized === '3minute') return 180;
  if (normalized === '5min' || normalized === '5minute') return 300;
  if (normalized === '10min' || normalized === '10minute') return 600;
  if (normalized === '15min' || normalized === '15minute') return 900;
  if (normalized === '30min' || normalized === '30minute') return 1800;
  if (normalized === '60min' || normalized === '60minute' || normalized === '1hour') return 3600;
  if (normalized === '1day' || normalized === 'day') return 86400;
  return 60;
}

function isOrderEventPlottable(status: string): boolean {
  const s = String(status || '').toUpperCase();
  return s === 'COMPLETED' || s === 'TRADE_CLOSED' || s === 'INFO' || s === 'EXECUTED';
}

function mapActionToMarker(actionInput: string): {
  text: 'BUY' | 'EXIT' | 'SHORT' | 'COVER';
  position: 'aboveBar' | 'belowBar' | 'inBar';
  color: string;
  shape: 'arrowUp' | 'arrowDown' | 'circle' | 'square';
} | null {
  const action = String(actionInput || '').toUpperCase();
  if (action.includes('BUY_ENTRY') || action === 'BUY') {
    return { text: 'BUY', position: 'belowBar', color: '#10B981', shape: 'arrowUp' };
  }
  if (action.includes('SELL_EXIT')) {
    return { text: 'EXIT', position: 'aboveBar', color: '#F97316', shape: 'arrowDown' };
  }
  if (action.includes('SELL_SHORT') || action === 'SHORT') {
    return { text: 'SHORT', position: 'aboveBar', color: '#EF4444', shape: 'arrowDown' };
  }
  if (action.includes('BUY_COVER') || action.includes('COVER')) {
    return { text: 'COVER', position: 'belowBar', color: '#22C55E', shape: 'arrowUp' };
  }
  return null;
}

function buildPriceOptions(catalog: CatalogEntry[]): PriceOption[] {
  const options: PriceOption[] = [];
  for (const instrument of catalog) {
    const symbol = instrument.tradingsymbol || `TOKEN ${instrument.instrument_token}`;
    for (const tf of instrument.timeframes_available || []) {
      const source = tf.data_source || 'historical';
      const id = `${instrument.instrument_token}|${tf.timeframe}|${tf.date_from}|${tf.date_to}|${source}`;
      const label = `${symbol} | ${instrument.instrument_token} | ${tf.timeframe} | ${tf.date_from} -> ${tf.date_to} | bars=${tf.total_bars} | ${source}`;
      options.push({
        id,
        label,
        searchText: `${symbol} ${instrument.instrument_token} ${tf.timeframe} ${tf.date_from} ${tf.date_to} ${source}`,
        instrument_token: instrument.instrument_token,
        tradingsymbol: symbol,
        timeframe: tf.timeframe,
        date_from: tf.date_from,
        date_to: tf.date_to,
        total_bars: tf.total_bars,
        data_source: source,
      });
    }
  }
  return options.sort((a, b) => a.label.localeCompare(b.label));
}

function buildResultOptions(results: BacktestResult[]): ResultOption[] {
  return results.map((result) => {
    const ds = result.data_selection;
    const symbol = ds?.tradingsymbol || result.symbol || `TOKEN ${ds?.instrument_token ?? '-'}`;
    const tf = ds?.timeframe || '-';
    const label = `${result.strategy_name} | ${result.task_id} | ${symbol} | ${tf} | ${result.status}`;
    return {
      id: result.task_id,
      task_id: result.task_id,
      label,
      searchText: `${result.strategy_name} ${result.task_id} ${symbol} ${tf} ${result.status} ${ds?.instrument_token ?? ''}`,
    };
  });
}

function ExpandIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M8 3H3V8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M16 3H21V8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M8 21H3V16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M16 21H21V16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function CollapseIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M3 8H8V3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M21 8H16V3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M3 16H8V21" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M21 16H16V21" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function resultMismatchWarning(price: PriceOption | null, result: BacktestResult | null): string | null {
  if (!price || !result || !result.data_selection) return null;
  const ds = result.data_selection;
  if (ds.instrument_token !== price.instrument_token) return 'Result instrument token does not match selected asset.';
  if (ds.timeframe !== price.timeframe) return 'Result timeframe does not match selected timeframe.';
  if (ds.date_from < price.date_from || ds.date_to > price.date_to) {
    return `Result range (${ds.date_from} to ${ds.date_to}) is outside selected chart range (${price.date_from} to ${price.date_to}).`;
  }
  return null;
}

function defaultParamsFor(meta: IndicatorMetadata): Record<string, number | string | boolean> {
  const out: Record<string, number | string | boolean> = {};
  for (const p of meta.params || []) {
    if (p.default != null) out[p.name] = p.default as number | string | boolean;
  }
  return out;
}

function paramsText(params: Record<string, number | string | boolean>): string {
  const entries = Object.entries(params);
  if (!entries.length) return 'default';
  return entries.map(([k, v]) => `${k}:${String(v)}`).join(', ');
}

function findPriceOptionByTokenAndTimeframe(
  options: PriceOption[],
  instrumentToken: number,
  timeframe: string,
): PriceOption | null {
  const matches = options.filter(
    (opt) => opt.instrument_token === instrumentToken && opt.timeframe === timeframe,
  );
  if (!matches.length) return null;
  return matches.sort((a, b) => b.date_to.localeCompare(a.date_to))[0];
}

function findPriceOptionForResult(
  options: PriceOption[],
  instrumentToken: number,
  timeframe: string,
  dateFrom: string,
  dateTo: string,
): PriceOption | null {
  const matches = options.filter(
    (opt) => opt.instrument_token === instrumentToken && opt.timeframe === timeframe,
  );
  if (!matches.length) return null;
  const covering = matches
    .filter((opt) => opt.date_from <= dateFrom && opt.date_to >= dateTo)
    .sort((a, b) => a.date_from.localeCompare(b.date_from) || b.date_to.localeCompare(a.date_to));
  if (covering.length) return covering[0];
  return matches.sort((a, b) => b.date_to.localeCompare(a.date_to))[0];
}

interface DashboardModuleProps {
  module: DashboardModuleState;
  onUpdate: (id: number, patch: Partial<DashboardModuleState>) => void;
  priceOptions: PriceOption[];
  resultOptions: ResultOption[];
  results: BacktestResult[];
  indicatorMeta: IndicatorMetadata[];
  backtestMode: boolean;
  liveMode: boolean;
}

function IndicatorDropdown({
  indicatorMeta,
  selectedIndicators,
  onToggle,
}: {
  indicatorMeta: IndicatorMetadata[];
  selectedIndicators: IndicatorSelection[];
  onToggle: (meta: IndicatorMetadata, checked: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const rootRef = useRef<HTMLDivElement | null>(null);
  const selectedNames = new Set(selectedIndicators.map((x) => x.name));

  useEffect(() => {
    if (!open) return;
    const onDocClick = (evt: MouseEvent) => {
      if (!rootRef.current) return;
      const target = evt.target as Node;
      if (!rootRef.current.contains(target)) setOpen(false);
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return indicatorMeta;
    return indicatorMeta.filter((meta) => {
      const hay = `${meta.name} ${meta.label} ${meta.category}`.toLowerCase();
      return hay.includes(q);
    });
  }, [indicatorMeta, query]);

  return (
    <div className="trd-indicator-search-root" ref={rootRef}>
      <div className="trd-indicator-search-shell">
        <input
          className="trd-indicator-search-input"
          placeholder="Search indicators..."
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onClick={() => setOpen(true)}
        />
        <button
          type="button"
          className="trd-indicator-search-clear"
          onClick={() => {
            setQuery('');
            setOpen(true);
          }}
        >
          Clear
        </button>
      </div>
      {open ? (
        <div className="trd-dropdown-panel">
          <div className="trd-indicator-list-head">
            <span>{selectedIndicators.length} selected</span>
            <button
              type="button"
              className="trd-indicator-search-clear small"
              onClick={() => setQuery('')}
            >
              Clear
            </button>
          </div>
          <div style={{ marginTop: 8, maxHeight: 250, overflowY: 'auto', display: 'grid', gap: 6 }}>
            {filtered.length ? filtered.map((meta) => {
              const checked = selectedNames.has(meta.name);
              return (
                <label
                  key={meta.name}
                  style={{
                    display: 'flex',
                    gap: 8,
                    alignItems: 'center',
                    fontSize: '0.82rem',
                    color: '#334155',
                    border: '1px solid #edf1f6',
                    borderRadius: 10,
                    padding: '8px 10px',
                    background: checked ? '#eef2ff' : '#fff',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(e) => onToggle(meta, e.target.checked)}
                  />
                  <span>{meta.label}</span>
                  <span style={{ marginLeft: 'auto', color: '#94a3b8', fontSize: '0.74rem' }}>
                    {meta.category}
                  </span>
                </label>
              );
            }) : (
              <div style={{ fontSize: '0.8rem', color: '#64748b', padding: '8px 4px' }}>
                No indicators found
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function DashboardModule({
  module,
  onUpdate,
  priceOptions,
  resultOptions,
  results,
  indicatorMeta,
  backtestMode,
  liveMode,
}: DashboardModuleProps) {
  const [bars, setBars] = useState<OHLCVBar[]>([]);
  const [loadingBars, setLoadingBars] = useState(false);
  const [barError, setBarError] = useState<string | null>(null);
  const [resultLoading, setResultLoading] = useState(false);
  const [resultError, setResultError] = useState<string | null>(null);
  const [selectedResultDetail, setSelectedResultDetail] = useState<BacktestResult | null>(null);
  const [indicatorSeries, setIndicatorSeries] = useState<IndicatorSeries[]>([]);
  const [indicatorWarning, setIndicatorWarning] = useState<string | null>(null);
  const [loadingIndicators, setLoadingIndicators] = useState(false);
  const [activeParamEditId, setActiveParamEditId] = useState<string | null>(null);
  const [tradeActionFilter, setTradeActionFilter] = useState<string>('ALL');
  const [tradeAssetFilter, setTradeAssetFilter] = useState('');
  const [tradePaneFullscreen, setTradePaneFullscreen] = useState(false);
  const [crosshairTime, setCrosshairTime] = useState<number | null>(null);
  const tradeLogRef = useRef<HTMLDivElement | null>(null);

  const selectedPrice = useMemo(
    () => priceOptions.find((p) => p.id === module.priceId) ?? null,
    [priceOptions, module.priceId],
  );
  const selectedResultSummary = useMemo(
    () => results.find((r) => r.task_id === module.tradeTaskId) ?? null,
    [results, module.tradeTaskId],
  );
  const selectedResult = selectedResultDetail ?? selectedResultSummary;
  const selectedTrades: Trade[] = useMemo(
    () => normalizeResultTrades(selectedResult),
    [selectedResult],
  );
  const selectedOrderEvents: OrderEvent[] = useMemo(
    () => normalizeOrderEvents(selectedResult),
    [selectedResult],
  );
  const selectedKpis = useMemo(
    () => normalizeResultKpis(selectedResult, selectedTrades),
    [selectedResult, selectedTrades],
  );

  const indicatorMetaMap = useMemo(() => {
    const map = new Map<string, IndicatorMetadata>();
    for (const meta of indicatorMeta) map.set(meta.name, meta);
    return map;
  }, [indicatorMeta]);

  useEffect(() => {
    let active = true;
    if (!module.tradeTaskId) {
      setSelectedResultDetail(null);
      setResultLoading(false);
      setResultError(null);
      return undefined;
    }
    const fetchDetail = async () => {
      setResultLoading(true);
      setResultError(null);
      setSelectedResultDetail(null);
      try {
        const response = await getBacktest(module.tradeTaskId);
        if (!active) return;
        setSelectedResultDetail(response as BacktestResult);
      } catch (e: unknown) {
        if (!active) return;
        setResultError(e instanceof Error ? e.message : 'Failed to load result detail');
      } finally {
        if (active) setResultLoading(false);
      }
    };
    fetchDetail();
    return () => {
      active = false;
    };
  }, [module.tradeTaskId]);

  useEffect(() => {
    if (!selectedResult?.data_selection) return;
    if (selectedPrice) return;
    const ds = selectedResult.data_selection;
    const match = findPriceOptionForResult(
      priceOptions,
      ds.instrument_token,
      ds.timeframe,
      ds.date_from,
      ds.date_to,
    );
    if (match && match.id !== module.priceId) {
      onUpdate(module.id, { priceId: match.id, chartRangeMode: 'full_result' });
    }
  }, [selectedResult, selectedPrice, priceOptions, module.id, module.priceId, onUpdate]);

  const resultRange = useMemo(() => {
    if (!selectedResult?.data_selection) return null;
    return selectedResult.data_selection;
  }, [selectedResult]);

  useEffect(() => {
    let active = true;
    const fetchBars = async () => {
      if (!selectedPrice) {
        setBars([]);
        return;
      }
      setLoadingBars(true);
      try {
        const response = await getHistoricalBars(
          selectedPrice.instrument_token,
          selectedPrice.timeframe,
          resultRange?.date_from || selectedPrice.date_from,
          resultRange?.date_to || selectedPrice.date_to,
        );
        if (!active) return;
        setBars(parseBars((response as { bars?: unknown }).bars));
        setBarError(null);
      } catch (e: unknown) {
        if (!active) return;
        setBarError(e instanceof Error ? e.message : 'Failed to load candles');
      } finally {
        if (active) setLoadingBars(false);
      }
    };
    fetchBars();
    return () => {
      active = false;
    };
  }, [selectedPrice, resultRange, module.syncNonce]);

  useEffect(() => {
    let active = true;
    const runIndicators = async () => {
      if (!selectedPrice || !module.selectedIndicators.length) {
        setIndicatorSeries([]);
        setIndicatorWarning(null);
        setLoadingIndicators(false);
        return;
      }
      setLoadingIndicators(true);
      try {
        const response = await computeIndicators({
          instrument_token: selectedPrice.instrument_token,
          timeframe: selectedPrice.timeframe,
          date_from: resultRange?.date_from || selectedPrice.date_from,
          date_to: resultRange?.date_to || selectedPrice.date_to,
          indicators: module.selectedIndicators.map((ind) => ({ name: ind.name, params: ind.params })),
        });
        if (!active) return;
        const raw = ((response as { series?: unknown[] }).series || []) as IndicatorSeries[];
        const cleaned = raw.map((s) => ({
          ...s,
          points: (s.points || [])
            .filter((p) => Number.isFinite(p.time) && Number.isFinite(p.value))
            .sort((a, b) => a.time - b.time),
        }));
        setIndicatorSeries(cleaned);
        const warnings = (response as { warnings?: string[] }).warnings || [];
        setIndicatorWarning(warnings.length ? warnings.join(' | ') : null);
      } catch (e: unknown) {
        if (!active) return;
        setIndicatorSeries([]);
        setIndicatorWarning(e instanceof Error ? e.message : 'Indicator compute failed');
      } finally {
        if (active) setLoadingIndicators(false);
      }
    };
    runIndicators();
    return () => {
      active = false;
    };
  }, [selectedPrice, resultRange, module.selectedIndicators, module.syncNonce]);

  const visibleBars = useMemo(() => {
    if (!bars.length) return [];
    if (module.chartRangeMode === 'full_result') return bars;
    if (module.chartRangeMode === 'last_1400') {
      return bars.length <= MAX_VISIBLE_CANDLES ? bars : bars.slice(-MAX_VISIBLE_CANDLES);
    }
    const days = module.chartRangeMode === 'last_5d' ? 5 : 20;
    const maxTime = bars[bars.length - 1].time;
    const minTime = maxTime - (days * 24 * 60 * 60);
    return bars.filter((bar) => bar.time >= minTime);
  }, [bars, module.chartRangeMode]);
  const candleTimes = useMemo(() => visibleBars.map((b) => b.time), [visibleBars]);
  const mismatchWarning = useMemo(
    () => resultMismatchWarning(selectedPrice, selectedResult),
    [selectedPrice, selectedResult],
  );

  const overlays = useMemo(
    () =>
      indicatorSeries
        .filter((s) => s.pane !== 'oscillator')
        .map((s) => ({
          key: s.id,
          label: s.label,
          color: s.color,
          data: s.points.map((p) => ({ time: p.time, value: p.value })),
        })),
    [indicatorSeries],
  );

  const oscillatorPanels = useMemo(() => {
    const grouped = new Map<string, Array<{ id: string; label: string; color: string; data: LinePoint[] }>>();
    for (const s of indicatorSeries) {
      if (s.pane !== 'oscillator') continue;
      const arr = grouped.get(s.name) || [];
      arr.push({
        id: s.id,
        label: s.label,
        color: s.color,
        data: s.points.map((p) => ({ time: p.time, value: p.value })),
      });
      grouped.set(s.name, arr);
    }
    return Array.from(grouped.entries()).map(([name, series]) => ({ name, series }));
  }, [indicatorSeries]);

  const markerResult = useMemo(() => {
    if (!module.plotSignals || !visibleBars.length || (!selectedTrades.length && !selectedOrderEvents.length)) {
      return {
        markers: [] as Array<{
          time: number;
          position: 'aboveBar' | 'belowBar' | 'inBar';
          color: string;
          shape: 'arrowUp' | 'arrowDown' | 'circle' | 'square';
          text: string;
        }>,
        diagnostics: {
          totalTrades: selectedTrades.length || selectedOrderEvents.length,
          rawMarkers: 0,
          collapsedMarkers: 0,
          markersPlotted: 0,
          outsideVisibleRange: 0,
          unmatchedTimestamps: 0,
        } as MarkerDiagnostics,
      };
    }
    const tolerance = timeframeToleranceSeconds(selectedPrice?.timeframe);
    const minTime = candleTimes[0];
    const maxTime = candleTimes[candleTimes.length - 1];
    let outside = 0;
    let unmatched = 0;
    const rawMarkers: Array<{
      time: number;
      position: 'aboveBar' | 'belowBar' | 'inBar';
      color: string;
      shape: 'arrowUp' | 'arrowDown' | 'circle' | 'square';
      text: string;
    }> = [];

    const pushMarker = (rawUnix: number | null, markerSeed: ReturnType<typeof mapActionToMarker>) => {
      if (rawUnix == null || markerSeed == null) {
        unmatched += 1;
        return;
      }
      const snapped = nearestCandleTime(rawUnix, candleTimes, tolerance);
      if (snapped == null) {
        unmatched += 1;
        return;
      }
      if (snapped < minTime || snapped > maxTime) {
        outside += 1;
        return;
      }
      rawMarkers.push({
        time: snapped,
        position: markerSeed.position,
        color: markerSeed.color,
        shape: markerSeed.shape,
        text: markerSeed.text,
      });
    };

    if (selectedOrderEvents.length) {
      for (const event of selectedOrderEvents) {
        if (!isOrderEventPlottable(event.status)) continue;
        const markerSeed = mapActionToMarker(event.action);
        if (!markerSeed) continue;
        pushMarker(normalizeTradeTimestampToUnix(event.time), markerSeed);
      }
    } else {
      for (const trade of selectedTrades) {
        const kind = directionKind(trade.direction);
        const entryAction = String(trade.entry_action || (kind === 'short' ? 'SELL_SHORT' : 'BUY')).toUpperCase();
        const exitAction = String(trade.exit_action || (kind === 'short' ? 'BUY_COVER' : 'SELL_EXIT')).toUpperCase();
        pushMarker(normalizeTradeTimestampToUnix(trade.entry_date), mapActionToMarker(entryAction));
        if (trade.exit_date) {
          pushMarker(normalizeTradeTimestampToUnix(trade.exit_date), mapActionToMarker(exitAction));
        }
      }
    }

    const grouped = new Map<string, { marker: typeof rawMarkers[number]; count: number }>();
    for (const marker of rawMarkers) {
      const key = `${marker.time}|${marker.position}|${marker.text}|${marker.shape}|${marker.color}`;
      const existing = grouped.get(key);
      if (!existing) grouped.set(key, { marker, count: 1 });
      else existing.count += 1;
    }
    const collapsed = Array.from(grouped.values()).map(({ marker, count }) => ({
      ...marker,
      text: count > 1 ? `${marker.text} x${count}` : marker.text,
    }));
    collapsed.sort((a, b) => a.time - b.time);

    return {
      markers: collapsed,
      diagnostics: {
        totalTrades: selectedTrades.length || selectedOrderEvents.length,
        rawMarkers: rawMarkers.length,
        collapsedMarkers: collapsed.length,
        markersPlotted: collapsed.length,
        outsideVisibleRange: outside,
        unmatchedTimestamps: unmatched,
      } as MarkerDiagnostics,
    };
  }, [module.plotSignals, visibleBars, selectedTrades, selectedOrderEvents, candleTimes, selectedPrice]);

  const closedTradeRows = useMemo(() => {
    const rows: Array<{
      id: number;
      direction: 'LONG' | 'SHORT';
      entryAction: string;
      entryTime: string;
      entryPrice: number | null;
      exitAction: string;
      exitTime: string;
      exitPrice: number | null;
      qty: number | null;
      netPnl: number | null;
      barsHeld: number | null;
      asset: string;
      isLatest: boolean;
    }> = [];
    let id = 1;
    for (const trade of selectedTrades) {
      const direction = directionKind(trade.direction) === 'short' ? 'SHORT' : 'LONG';
      const entryAction = String(trade.entry_action || (direction === 'SHORT' ? 'SELL_SHORT' : 'BUY')).toUpperCase();
      const exitAction = String(trade.exit_action || (direction === 'SHORT' ? 'BUY_COVER' : 'SELL_EXIT')).toUpperCase();
      const asset = trade.symbol || selectedPrice?.tradingsymbol || selectedResult?.symbol || '-';
      const actionKey = `${entryAction}|${exitAction}|${direction}`;
      if (tradeActionFilter !== 'ALL' && !actionKey.includes(tradeActionFilter)) continue;
      if (tradeAssetFilter.trim() && !asset.toLowerCase().includes(tradeAssetFilter.trim().toLowerCase())) continue;
      rows.push({
        id: id++,
        direction,
        entryAction,
        entryTime: trade.entry_date || '-',
        entryPrice: Number.isFinite(trade.entry_price) ? trade.entry_price : null,
        exitAction,
        exitTime: trade.exit_date || '-',
        exitPrice: Number.isFinite(trade.exit_price) ? trade.exit_price : null,
        qty: Number.isFinite(trade.quantity ?? trade.size) ? Number(trade.quantity ?? trade.size) : null,
        netPnl: Number.isFinite(trade.net_pnl ?? trade.pnl) ? Number(trade.net_pnl ?? trade.pnl) : null,
        barsHeld: Number.isFinite(trade.bars_held) ? Number(trade.bars_held) : null,
        asset,
        isLatest: false,
      });
    }
    const reversed = rows.slice().reverse();
    return reversed.map((row, idx) => ({ ...row, isLatest: idx < 3 }));
  }, [selectedTrades, selectedPrice, selectedResult, tradeActionFilter, tradeAssetFilter]);

  const orderEventRows = useMemo(() => {
    const rows: Array<{
      id: number;
      time: string;
      action: string;
      status: string;
      qty: number | null;
      price: number | null;
      posBefore: number | null;
      posAfter: number | null;
      reason: string;
      asset: string;
      isLatest: boolean;
    }> = [];
    let id = 1;
    for (const event of selectedOrderEvents) {
      const action = String(event.action || 'UNKNOWN').toUpperCase();
      const status = String(event.status || 'UNKNOWN').toUpperCase();
      const asset = selectedPrice?.tradingsymbol || selectedResult?.symbol || '-';
      if (tradeActionFilter !== 'ALL' && !(action.includes(tradeActionFilter) || status.includes(tradeActionFilter))) continue;
      if (tradeAssetFilter.trim() && !asset.toLowerCase().includes(tradeAssetFilter.trim().toLowerCase())) continue;
      rows.push({
        id: id++,
        time: event.time || '-',
        action,
        status,
        qty: Number.isFinite(event.executed_size ?? event.requested_size) ? Number(event.executed_size ?? event.requested_size) : null,
        price: Number.isFinite(event.price) ? Number(event.price) : null,
        posBefore: Number.isFinite(event.position_before) ? Number(event.position_before) : null,
        posAfter: Number.isFinite(event.position_after) ? Number(event.position_after) : null,
        reason: event.reason || '-',
        asset,
        isLatest: false,
      });
    }
    const reversed = rows.slice().reverse();
    return reversed.map((row, idx) => ({ ...row, isLatest: idx < 3 }));
  }, [selectedOrderEvents, selectedPrice, selectedResult, tradeActionFilter, tradeAssetFilter]);

  const tradebookActionOptions = useMemo(() => {
    if (module.tradebookMode === 'order_events') {
      const actions = new Set<string>(['ALL']);
      for (const event of selectedOrderEvents) {
        const action = String(event.action || '').toUpperCase();
        if (action) actions.add(action);
        const status = String(event.status || '').toUpperCase();
        if (status) actions.add(status);
      }
      return Array.from(actions).slice(0, 14);
    }
    const actions = new Set<string>(['ALL']);
    for (const trade of selectedTrades) {
      actions.add(String(trade.entry_action || '').toUpperCase() || 'BUY');
      actions.add(String(trade.exit_action || '').toUpperCase() || 'SELL_EXIT');
      actions.add(directionKind(trade.direction) === 'short' ? 'SHORT' : 'LONG');
    }
    return Array.from(actions).slice(0, 14);
  }, [module.tradebookMode, selectedOrderEvents, selectedTrades]);

  useEffect(() => {
    if (tradebookActionOptions.includes(tradeActionFilter)) return;
    setTradeActionFilter('ALL');
  }, [tradebookActionOptions, tradeActionFilter]);

  const toggleIndicator = (meta: IndicatorMetadata, checked: boolean) => {
    if (checked) {
      const next: IndicatorSelection = {
        id: `${meta.name}-${Date.now()}`,
        name: meta.name,
        label: meta.label,
        pane: meta.pane,
        params: defaultParamsFor(meta),
      };
      onUpdate(module.id, { selectedIndicators: [...module.selectedIndicators, next] });
      return;
    }
    onUpdate(module.id, {
      selectedIndicators: module.selectedIndicators.filter((ind) => ind.name !== meta.name),
    });
  };

  const timeframeOptions = useMemo(() => {
    if (!selectedPrice) return [];
    const timeframes = priceOptions
      .filter((opt) => opt.instrument_token === selectedPrice.instrument_token)
      .map((opt) => opt.timeframe);
    return Array.from(new Set(timeframes));
  }, [selectedPrice, priceOptions]);

  const indicatorSummary = useMemo(() => {
    if (!module.selectedIndicators.length) return 'No indicators';
    return module.selectedIndicators.map((i) => i.label).slice(0, 3).join(', ');
  }, [module.selectedIndicators]);

  useEffect(() => {
    if (!tradeLogRef.current) return;
    tradeLogRef.current.scrollTop = 0;
  }, [closedTradeRows, orderEventRows, module.tradebookMode]);

  useEffect(() => {
    if (!tradePaneFullscreen) return;
    const onEsc = (evt: KeyboardEvent) => {
      if (evt.key === 'Escape') setTradePaneFullscreen(false);
    };
    window.addEventListener('keydown', onEsc);
    return () => window.removeEventListener('keydown', onEsc);
  }, [tradePaneFullscreen]);

  return (
    <section className="trd-module">
      <div className="trd-toolbar">
        <div className="trd-tool trd-tool-asset">
          <div className="trd-tool-label">Asset</div>
          <SearchableDropdown
            label=""
            value={module.priceId}
            options={priceOptions}
            onChange={(next) => onUpdate(module.id, { priceId: next })}
            placeholder="Asset"
          />
        </div>

        <div className="trd-tool trd-tool-timeframes">
          {timeframeOptions.length ? (
            timeframeOptions.slice(0, 6).map((tf) => (
              <button
                key={`${module.id}-tf-${tf}`}
                type="button"
                className={`trd-tf-btn ${selectedPrice?.timeframe === tf ? 'active' : ''}`}
                onClick={() => {
                  if (!selectedPrice) return;
                  const next = findPriceOptionByTokenAndTimeframe(priceOptions, selectedPrice.instrument_token, tf);
                  if (next) onUpdate(module.id, { priceId: next.id });
                }}
              >
                {tf}
              </button>
            ))
          ) : (
            <span className="trd-muted">Timeframe</span>
          )}
        </div>

        <div className="trd-tool trd-tool-date">
          <div className="trd-readonly-control">
            {selectedPrice ? `${selectedPrice.date_from} to ${selectedPrice.date_to}` : 'Date Range'}
          </div>
        </div>

        <div className="trd-tool trd-tool-indicators">
          <IndicatorDropdown
            indicatorMeta={indicatorMeta}
            selectedIndicators={module.selectedIndicators}
            onToggle={toggleIndicator}
          />
        </div>

        <div className="trd-tool trd-tool-compare">
          <div className="trd-tool-label">Compare Result</div>
          <SearchableDropdown
            label=""
            value={module.tradeTaskId}
            options={resultOptions}
            onChange={(next) => onUpdate(module.id, { tradeTaskId: next })}
            placeholder="Compare"
          />
        </div>
      </div>

      <div className="trd-chip-wrap">
        {module.selectedIndicators.map((ind) => (
          <div key={ind.id} className="trd-chip">
            <span>{ind.label}</span>
            <button
              type="button"
              onClick={() => setActiveParamEditId((prev) => (prev === ind.id ? null : ind.id))}
              className="trd-chip-btn"
            >
              Edit
            </button>
            <button
              type="button"
              onClick={() =>
                onUpdate(module.id, {
                  selectedIndicators: module.selectedIndicators.filter((x) => x.id !== ind.id),
                })
              }
              className="trd-chip-btn"
            >
              Remove
            </button>
          </div>
        ))}
      </div>

      <div className="trd-kpi-row">
        <div className="trd-kpi-item">
          <span className="trd-kpi-label">Final Value</span>
          <span className="trd-kpi-value">{formatMetricValue(selectedKpis.finalValue, 'currency')}</span>
        </div>
        <div className="trd-kpi-item">
          <span className="trd-kpi-label">Net PnL</span>
          <span className={`trd-kpi-value ${selectedKpis.netPnl != null && selectedKpis.netPnl < 0 ? 'neg' : 'pos'}`}>
            {formatMetricValue(selectedKpis.netPnl, 'currency')}
          </span>
        </div>
        <div className="trd-kpi-item">
          <span className="trd-kpi-label">Return</span>
          <span className={`trd-kpi-value ${selectedKpis.returnPct != null && selectedKpis.returnPct < 0 ? 'neg' : 'pos'}`}>
            {formatMetricValue(selectedKpis.returnPct, 'percent')}
          </span>
        </div>
        <div className="trd-kpi-item">
          <span className="trd-kpi-label">Trades</span>
          <span className="trd-kpi-value">{formatMetricValue(selectedKpis.totalTrades, 'number')}</span>
        </div>
        <div className="trd-kpi-item">
          <span className="trd-kpi-label">Win Rate</span>
          <span className="trd-kpi-value">{formatMetricValue(selectedKpis.winRate, 'percent')}</span>
        </div>
        <div className="trd-kpi-item">
          <span className="trd-kpi-label">Max DD</span>
          <span className="trd-kpi-value">{formatMetricValue(selectedKpis.maxDrawdown, 'percent')}</span>
        </div>
        <div className="trd-kpi-item">
          <span className="trd-kpi-label">Sharpe</span>
          <span className="trd-kpi-value">{formatMetricValue(selectedKpis.sharpeRatio, 'ratio')}</span>
        </div>
        <div className="trd-kpi-item">
          <span className="trd-kpi-label">Profit Factor</span>
          <span className="trd-kpi-value">{formatMetricValue(selectedKpis.profitFactor, 'ratio')}</span>
        </div>
      </div>

      {activeParamEditId ? (
        <div className="trd-param-panel">
          {module.selectedIndicators.filter((x) => x.id === activeParamEditId).map((selected) => {
            const meta = indicatorMetaMap.get(selected.name);
            if (!meta) return null;
            return (
              <div key={`${selected.id}-edit`}>
                <div className="trd-param-summary">{paramsText(selected.params)}</div>
                <div className="trd-param-grid">
                  {(meta.params || []).slice(0, 4).map((param) => (
                    <label key={`${selected.id}-${param.name}`} style={{ display: 'grid', gap: 4 }}>
                      <span className="trd-label">{param.name}</span>
                      <input
                        className="input"
                        type={param.type === 'number' ? 'number' : 'text'}
                        min={param.min}
                        max={param.max}
                        value={String(selected.params[param.name] ?? param.default ?? '')}
                        onChange={(e) => {
                          const raw = e.target.value;
                          const val = param.type === 'number' ? Number(raw) : raw;
                          onUpdate(module.id, {
                            selectedIndicators: module.selectedIndicators.map((x) =>
                              x.id === selected.id ? { ...x, params: { ...x.params, [param.name]: val } } : x,
                            ),
                          });
                        }}
                      />
                    </label>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      ) : null}

      {mismatchWarning ? <div className="trd-warning">{mismatchWarning}</div> : null}
      {selectedResult && Number(selectedResult.result_schema_version || 1) < 2 ? (
        <div className="trd-warning">Legacy result detected: direction semantics may be ambiguous for older runs.</div>
      ) : null}
      {resultLoading ? <div className="trd-muted">Loading selected result output...</div> : null}
      {resultError ? <div className="trd-error">{resultError}</div> : null}
      {barError ? (
        <div className="trd-error">
          {barError} | Try switching timeframe or refresh catalog data.
        </div>
      ) : null}

      <div className="trd-context-strip">
        <span className="trd-context-item"><strong>Asset:</strong> {selectedPrice?.tradingsymbol || 'Not selected'}</span>
        <span className="trd-context-item"><strong>Timeframe:</strong> {selectedPrice?.timeframe || '-'}</span>
        <span className="trd-context-item"><strong>Indicators:</strong> {indicatorSummary}</span>
        <span className="trd-context-item"><strong>Mode:</strong> {backtestMode ? 'Backtest' : 'Review'} / {liveMode ? 'Live' : 'Paused'}</span>
        {(loadingBars || loadingIndicators) ? <span className="trd-context-live">Updating...</span> : null}
      </div>

      <div className="trd-main-grid">
        <div className="trd-chart-pane">
          <div className="trd-chart-header">
            <div>
              <div className="trd-chart-symbol">{selectedPrice?.tradingsymbol || 'Asset'}</div>
              <div className="trd-muted">
                {selectedPrice?.timeframe || '-'} | {indicatorSummary}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              <label className="trd-toggle">
                <input
                  type="checkbox"
                  checked={module.plotSignals}
                  onChange={(e) => onUpdate(module.id, { plotSignals: e.target.checked })}
                />
                Plot Buy/Sell
              </label>
              <select
                className="trd-mini-filter"
                value={module.chartRangeMode}
                onChange={(e) =>
                  onUpdate(module.id, {
                    chartRangeMode: e.target.value as DashboardModuleState['chartRangeMode'],
                  })}
              >
                <option value="full_result">Full Result</option>
                <option value="last_1400">Last 1400</option>
                <option value="last_5d">Last 5D</option>
                <option value="last_20d">Last 20D</option>
              </select>
              <button className="btn btn-ghost btn-sm" onClick={() => onUpdate(module.id, { syncNonce: module.syncNonce + 1 })}>
                {loadingBars || loadingIndicators ? 'Syncing...' : 'Sync'}
              </button>
            </div>
          </div>

          <div className="trd-diag">
            loaded {bars.length} | visible {visibleBars.length}
            {selectedResult?.data_selection ? ` | result ${selectedResult.data_selection.date_from} to ${selectedResult.data_selection.date_to}` : ''}
            {visibleBars.length ? ` | chart ${new Date(visibleBars[0].time * 1000).toLocaleDateString('en-IN')} to ${new Date(visibleBars[visibleBars.length - 1].time * 1000).toLocaleDateString('en-IN')}` : ''}
            | markers {markerResult.diagnostics.markersPlotted} (raw {markerResult.diagnostics.rawMarkers}, collapsed {markerResult.diagnostics.collapsedMarkers})
            | outside {markerResult.diagnostics.outsideVisibleRange} | unmatched {markerResult.diagnostics.unmatchedTimestamps}
            {crosshairTime ? ` | cursor ${new Date(crosshairTime * 1000).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}` : ''}
          </div>

          {indicatorWarning ? <div className="trd-warning">{indicatorWarning}</div> : null}
          {loadingBars ? (
            <div className="trd-skeleton-wrap">
              <div className="trd-skeleton trd-skeleton-chart" />
              <div className="trd-skeleton trd-skeleton-line" />
            </div>
          ) : visibleBars.length ? (
            <>
              <LightweightCandlestickChart
                bars={visibleBars}
                symbol={selectedPrice?.tradingsymbol || 'Instrument'}
                overlays={overlays}
                markers={markerResult.markers}
                onCrosshairTime={setCrosshairTime}
              />
              {oscillatorPanels.map((panel) => (
                <div key={`${module.id}-osc-${panel.name}`} style={{ marginTop: 10 }}>
                  <LightweightLineChart title={panel.name.toUpperCase()} series={panel.series} height={145} />
                </div>
              ))}
            </>
          ) : (
            <div className="trd-muted">Select pricing data to render chart.</div>
          )}
        </div>

        <aside className={`trd-trade-pane ${tradePaneFullscreen ? 'trd-trade-pane-fullscreen' : ''}`}>
          <div className="trd-trade-header">
            <div className="trd-trade-title-row">
              <div className="trd-trade-title">{module.tradebookMode === 'closed_trades' ? 'Trade Book' : 'Order Events'}</div>
              <button
                type="button"
                className="trd-icon-btn"
                onClick={() => setTradePaneFullscreen((prev) => !prev)}
                aria-label={tradePaneFullscreen ? 'Collapse trade table' : 'Expand trade table'}
                title={tradePaneFullscreen ? 'Exit Full Screen (Esc)' : 'Full Screen'}
              >
                {tradePaneFullscreen ? <CollapseIcon /> : <ExpandIcon />}
              </button>
            </div>
            <div className="trd-trade-filters">
              <select
                className="trd-mini-filter"
                value={module.tradebookMode}
                onChange={(e) => onUpdate(module.id, { tradebookMode: e.target.value as DashboardModuleState['tradebookMode'] })}
              >
                <option value="closed_trades">Closed Trades</option>
                <option value="order_events">Order Events</option>
              </select>
              <select
                className="trd-mini-filter"
                value={tradeActionFilter}
                onChange={(e) => setTradeActionFilter(e.target.value)}
              >
                {tradebookActionOptions.map((opt) => (
                  <option key={`${module.id}-action-${opt}`} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>
              <input
                className="trd-mini-filter"
                value={tradeAssetFilter}
                onChange={(e) => setTradeAssetFilter(e.target.value)}
                placeholder="Asset"
              />
            </div>
          </div>
          <div className="trd-trade-wrap" ref={tradeLogRef}>
            <table className="trd-trade-table">
              <thead>
                {module.tradebookMode === 'closed_trades' ? (
                  <tr>
                    <th>#</th>
                    <th>Dir</th>
                    <th>Entry</th>
                    <th>Entry Time</th>
                    <th>Entry Px</th>
                    <th>Exit</th>
                    <th>Exit Time</th>
                    <th>Exit Px</th>
                    <th>Qty</th>
                    <th>Net PnL</th>
                  </tr>
                ) : (
                  <tr>
                    <th>#</th>
                    <th>Time</th>
                    <th>Action</th>
                    <th>Status</th>
                    <th>Qty</th>
                    <th>Price</th>
                    <th>Pos</th>
                    <th>Reason</th>
                  </tr>
                )}
              </thead>
              <tbody>
                {(loadingBars || loadingIndicators || resultLoading) ? (
                  Array.from({ length: 8 }).map((_, idx) => (
                    <tr key={`${module.id}-skeleton-${idx}`}>
                      <td colSpan={module.tradebookMode === 'closed_trades' ? 10 : 8}><div className="trd-skeleton trd-skeleton-row" /></td>
                    </tr>
                  ))
                ) : module.tradebookMode === 'closed_trades' && closedTradeRows.length ? (
                  closedTradeRows.map((row) => (
                    <tr key={`${module.id}-trade-${row.id}-${row.entryTime}`} className={row.isLatest ? 'trd-row-latest' : ''}>
                      <td>{row.id}</td>
                      <td>
                        <span className={`trd-badge ${row.direction === 'LONG' ? 'buy' : 'sell'}`}>{row.direction}</span>
                      </td>
                      <td className="trd-mono">{row.entryAction}</td>
                      <td className="trd-mono">{row.entryTime}</td>
                      <td className="trd-mono">{row.entryPrice != null ? row.entryPrice.toFixed(2) : '-'}</td>
                      <td className="trd-mono">{row.exitAction}</td>
                      <td className="trd-mono">{row.exitTime}</td>
                      <td className="trd-mono">{row.exitPrice != null ? row.exitPrice.toFixed(2) : '-'}</td>
                      <td className="trd-mono">{row.qty != null ? row.qty.toFixed(2) : '-'}</td>
                      <td className={`trd-mono ${(row.netPnl ?? 0) < 0 ? 'trd-neg' : 'trd-pos'}`}>{row.netPnl != null ? row.netPnl.toFixed(2) : '-'}</td>
                    </tr>
                  ))
                ) : module.tradebookMode === 'order_events' && orderEventRows.length ? (
                  orderEventRows.map((row) => (
                    <tr key={`${module.id}-evt-${row.id}-${row.time}`} className={row.isLatest ? 'trd-row-latest' : ''}>
                      <td>{row.id}</td>
                      <td className="trd-mono">{row.time}</td>
                      <td className="trd-mono">{row.action}</td>
                      <td className="trd-mono">{row.status}</td>
                      <td className="trd-mono">{row.qty != null ? row.qty.toFixed(2) : '-'}</td>
                      <td className="trd-mono">{row.price != null ? row.price.toFixed(2) : '-'}</td>
                      <td className="trd-mono">
                        {row.posBefore != null || row.posAfter != null ? `${row.posBefore ?? '-'} -> ${row.posAfter ?? '-'}` : '-'}
                      </td>
                      <td title={row.reason}>{row.reason || '-'}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={module.tradebookMode === 'closed_trades' ? 10 : 8} style={{ textAlign: 'center', color: '#64748b', padding: 14 }}>
                      {module.tradeTaskId
                        ? (module.tradebookMode === 'closed_trades' ? 'No closed trades found in selected result' : 'No order events found in selected result')
                        : 'No result selected'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </aside>
      </div>
    </section>
  );
}

export default function Dashboard() {
  const [catalog, setCatalog] = useState<CatalogEntry[]>([]);
  const [results, setResults] = useState<BacktestResult[]>([]);
  const [indicatorMeta, setIndicatorMeta] = useState<IndicatorMetadata[]>([]);
  const [modules, setModules] = useState<DashboardModuleState[]>([
    {
      id: 1,
      priceId: '',
      tradeTaskId: '',
      selectedIndicators: [],
      plotSignals: false,
      syncNonce: 0,
      chartRangeMode: 'full_result',
      tradebookMode: 'closed_trades',
    },
  ]);
  const [error, setError] = useState<string | null>(null);
  const [backtestMode] = useState(true);
  const [liveMode] = useState(true);

  const refreshDashboardData = async () => {
    const [catalogResp, resultResp, indicatorResp] = await Promise.all([
      getCatalog(),
      getBacktests(),
      getIndicators(),
    ]);
    setCatalog((catalogResp.catalog || []) as CatalogEntry[]);
    const sorted = ((resultResp.results || []) as BacktestResult[])
      .slice()
      .sort((a, b) => {
        const at = Date.parse(a.started_at || '');
        const bt = Date.parse(b.started_at || '');
        return (Number.isFinite(bt) ? bt : 0) - (Number.isFinite(at) ? at : 0);
      });
    setResults(sorted);
    setIndicatorMeta((indicatorResp.indicators || []) as IndicatorMetadata[]);
  };

  useEffect(() => {
    let active = true;
    const run = async () => {
      try {
        await refreshDashboardData();
        if (!active) return;
        setError(null);
      } catch (e: unknown) {
        if (!active) return;
        setError(e instanceof Error ? e.message : 'Failed to load dashboard');
      }
    };
    run();
    return () => {
      active = false;
    };
  }, []);

  const priceOptions = useMemo(() => buildPriceOptions(catalog), [catalog]);
  const resultOptions = useMemo(() => buildResultOptions(results), [results]);

  useEffect(() => {
    setModules((prev) =>
      prev.map((m) => ({
        ...m,
        priceId: priceOptions.some((o) => o.id === m.priceId) ? m.priceId : '',
        tradeTaskId: resultOptions.some((o) => o.id === m.tradeTaskId) ? m.tradeTaskId : '',
      })),
    );
  }, [priceOptions, resultOptions]);

  const updateModule = (id: number, patch: Partial<DashboardModuleState>) => {
    setModules((prev) => prev.map((m) => (m.id === id ? { ...m, ...patch } : m)));
  };

  const addModule = () => {
    setModules((prev) => [
      ...prev,
      {
        id: prev.length + 1,
        priceId: '',
        tradeTaskId: '',
        selectedIndicators: [],
        plotSignals: false,
        syncNonce: 0,
        chartRangeMode: 'full_result',
        tradebookMode: 'closed_trades',
      },
    ]);
  };

  return (
    <div className="trd-root animate-in">
      <style>{`
        .trd-root { min-height: 100%; background: #FAFAFB; padding: 8px 10px 84px; }
        .trd-module { margin-bottom: 12px; }

        .trd-toolbar {
          display: grid;
          grid-template-columns: minmax(200px, 2.2fr) minmax(160px, 1fr) minmax(180px, 1.2fr) minmax(180px, 1.25fr) minmax(180px, 1.25fr);
          gap: 8px;
          border-bottom: 1px solid #F1F5F9;
          padding: 4px 0 10px;
          margin-bottom: 8px;
          align-items: center;
        }
        .trd-tool-asset, .trd-tool-timeframes { grid-column: auto; }
        .trd-tool-indicators { grid-column: auto; }
        .trd-tool-compare { grid-column: auto; }
        .trd-tool { position: relative; min-width: 0; }
        .trd-tool .stat-label { display: none; }
        .trd-tool-label {
          font-size: 11px;
          font-weight: 600;
          color: #334155;
          margin-bottom: 4px;
          line-height: 1;
        }
        .trd-tool .input {
          height: 40px;
          min-height: 40px;
          border: 1px solid #E5E7EB;
          border-radius: 8px;
          font-size: 13px;
          background: #FAFAFB;
          transition: border-color 200ms ease, background-color 200ms ease;
        }
        .trd-tool .input:hover { border-color: #d5d9e0; }
        .trd-tool .input:focus {
          outline: none;
          border-color: #c7d2fe;
          box-shadow: 0 0 0 2px rgba(79, 70, 229, 0.1);
        }
        .trd-indicator-search-root { position: relative; }
        .trd-indicator-search-shell {
          height: 38px;
          border: 1px solid #E5E7EB;
          border-radius: 8px;
          background: #FAFAFB;
          display: flex;
          align-items: center;
          padding: 0 6px 0 10px;
          gap: 6px;
        }
        .trd-indicator-search-shell:focus-within {
          border-color: #c7d2fe;
          box-shadow: 0 0 0 2px rgba(79, 70, 229, 0.1);
        }
        .trd-indicator-search-input {
          flex: 1;
          border: 0;
          outline: none;
          background: transparent;
          color: #0f172a;
          font-size: 13px;
        }
        .trd-indicator-search-input::placeholder { color: #94a3b8; }
        .trd-indicator-search-clear {
          border: 1px solid #E5E7EB;
          background: #FFFFFF;
          color: #64748b;
          border-radius: 6px;
          font-size: 11px;
          padding: 2px 8px;
          cursor: pointer;
          transition: all 200ms ease;
        }
        .trd-indicator-search-clear:hover {
          color: #4F46E5;
          border-color: #c7d2fe;
          background: #eef2ff;
        }
        .trd-indicator-search-clear.small {
          font-size: 10px;
          padding: 1px 6px;
        }
        .trd-indicator-list-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          border-bottom: 1px solid #F1F5F9;
          padding-bottom: 6px;
          font-size: 12px;
          color: #64748b;
        }

        .trd-pill-input {
          width: 100%;
          height: 38px;
          border-radius: 8px;
          border: 1px solid #E5E7EB;
          background: #FAFAFB;
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0 12px;
          font-size: 13px;
          transition: border-color 200ms ease;
        }
        .trd-pill-input:hover { border-color: #d5d9e0; }
        .trd-dropdown-panel {
          position: absolute;
          left: 0;
          right: 0;
          top: 44px;
          border: 1px solid #e5e7eb;
          border-radius: 10px;
          background: #FAFAFB;
          padding: 8px;
          z-index: 24;
          animation: trd-dropdown-in 180ms ease;
        }
        @keyframes trd-dropdown-in {
          from { opacity: 0; transform: translateY(-3px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .trd-timeframe-row {
          display: flex;
          align-items: center;
          gap: 6px;
          flex-wrap: nowrap;
          overflow-x: auto;
          padding: 2px;
        }
        .trd-tf-btn {
          border: 1px solid #E5E7EB;
          border-radius: 8px;
          background: #FFFFFF;
          color: #64748b;
          font-size: 12px;
          padding: 3px 8px;
          cursor: pointer;
          transition: all 200ms ease;
        }
        .trd-tf-btn.active {
          color: #4f46e5;
          border-color: #c7d2fe;
          background: #eef2ff;
          font-weight: 600;
        }
        .trd-readonly-control {
          height: 38px;
          border: 1px solid #E5E7EB;
          border-radius: 8px;
          background: #FAFAFB;
          display: flex;
          align-items: center;
          padding: 0 12px;
          font-size: 13px;
          color: #334155;
        }
        .trd-context-strip {
          display: flex;
          gap: 10px;
          flex-wrap: wrap;
          align-items: center;
          border-top: 1px solid #F1F5F9;
          border-bottom: 1px solid #F1F5F9;
          padding: 8px 2px;
          margin: 0 0 10px 0;
        }
        .trd-context-item {
          font-size: 12px;
          color: #475569;
          white-space: nowrap;
        }
        .trd-context-item strong {
          color: #0f172a;
          font-weight: 600;
        }
        .trd-context-live {
          margin-left: auto;
          font-size: 12px;
          color: #4F46E5;
          font-weight: 600;
        }
        .trd-chip-wrap {
          margin-top: 8px;
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
        }
        .trd-chip {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          border: 1px solid #F1F5F9;
          background: transparent;
          border-radius: 999px;
          padding: 4px 8px;
          color: #4F46E5;
          font-size: 12px;
        }
        .trd-chip-btn {
          border: 0;
          background: transparent;
          color: #4338ca;
          font-size: 11px;
          cursor: pointer;
          padding: 0;
        }
        .trd-kpi-row {
          margin-top: 8px;
          display: grid;
          grid-template-columns: repeat(8, minmax(0, 1fr));
          gap: 8px;
        }
        .trd-kpi-item {
          border: 1px solid #F1F5F9;
          border-radius: 8px;
          padding: 8px;
          background: transparent;
          display: grid;
          gap: 4px;
          min-height: 58px;
        }
        .trd-kpi-label {
          font-size: 11px;
          color: #64748b;
          text-transform: uppercase;
          letter-spacing: 0.02em;
        }
        .trd-kpi-value {
          font-size: 13px;
          color: #0f172a;
          font-weight: 600;
          font-family: var(--font-mono);
        }
        .trd-kpi-value.pos { color: #0f766e; }
        .trd-kpi-value.neg { color: #b91c1c; }
        .trd-param-panel {
          margin-top: 8px;
          border: 1px solid #F1F5F9;
          border-radius: 8px;
          background: transparent;
          padding: 10px;
        }
        .trd-param-summary { font-size: 0.74rem; color: #64748b; margin-bottom: 6px; }
        .trd-param-grid {
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 8px;
        }
        .trd-label { font-size: 0.74rem; color: #6b7280; }
        .trd-warning {
          font-size: 0.78rem;
          color: #b45309;
          margin: 2px 0 8px;
        }
        .trd-error {
          font-size: 0.78rem;
          color: #dc2626;
          margin: 2px 0 10px;
        }
        .trd-muted { color: #64748b; font-size: 0.84rem; }

        .trd-main-grid {
          display: grid;
          grid-template-columns: minmax(0, 74fr) minmax(280px, 26fr);
          gap: 16px;
        }
        .trd-chart-pane {
          border: 1px solid #F1F5F9;
          border-radius: 9px;
          background: transparent;
          padding: 8px 10px;
        }
        .trd-chart-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 6px;
        }
        .trd-chart-symbol {
          font-size: 16px;
          color: #0f172a;
          font-weight: 600;
        }
        .trd-toggle {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          color: #334155;
          font-size: 13px;
        }
        .trd-diag {
          font-size: 12px;
          color: #64748b;
          border-bottom: 1px solid #f1f5f9;
          padding-bottom: 4px;
          margin-bottom: 5px;
        }

        .trd-trade-pane {
          border: 1px solid #F1F5F9;
          border-radius: 9px;
          background: transparent;
          padding: 8px 10px;
          min-height: 590px;
        }
        .trd-trade-pane-fullscreen {
          position: fixed;
          top: 78px;
          left: 12px;
          right: 12px;
          bottom: 12px;
          z-index: 80;
          background: #FAFAFB;
          border-color: #E5E7EB;
          border-radius: 12px;
          min-height: 0;
        }
        .trd-trade-pane-fullscreen .trd-trade-wrap {
          max-height: calc(100vh - 170px);
        }
        .trd-trade-title {
          font-size: 16px;
          color: #111827;
          font-weight: 600;
          margin-bottom: 0;
        }
        .trd-trade-title-row {
          display: inline-flex;
          align-items: center;
          gap: 6px;
        }
        .trd-icon-btn {
          height: 26px;
          width: 26px;
          border: 1px solid #E5E7EB;
          border-radius: 7px;
          background: #FFFFFF;
          color: #64748b;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          transition: all 200ms ease;
        }
        .trd-icon-btn:hover {
          color: #4F46E5;
          border-color: #c7d2fe;
          background: #eef2ff;
        }
        .trd-trade-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 8px;
          margin-bottom: 6px;
        }
        .trd-trade-filters {
          display: inline-flex;
          align-items: center;
          gap: 6px;
        }
        .trd-mini-filter {
          height: 28px;
          border: 1px solid #E5E7EB;
          border-radius: 6px;
          background: #FAFAFB;
          color: #334155;
          font-size: 12px;
          padding: 0 8px;
          min-width: 72px;
        }
        .trd-trade-wrap { max-height: 560px; overflow: auto; }
        .trd-trade-table {
          width: 100%;
          border-collapse: collapse;
          font-size: 12.5px;
        }
        .trd-trade-table th {
          position: sticky;
          top: 0;
          z-index: 1;
          background: #FAFAFB;
          text-align: left;
          padding: 7px 6px;
          border-bottom: 1px solid #e5e7eb;
          color: #64748b;
          font-size: 11px;
          text-transform: uppercase;
        }
        .trd-trade-table td {
          padding: 6px 6px;
          border-bottom: 1px solid #f1f5f9;
          color: #334155;
        }
        .trd-trade-table tr:hover td { background: #f8fafc; }
        .trd-row-latest td {
          background: #f8fafc;
          animation: trd-new-row 350ms ease;
        }
        @keyframes trd-new-row {
          from { background: #eef2ff; }
          to { background: #f8fafc; }
        }
        .trd-badge {
          display: inline-flex;
          align-items: center;
          border-radius: 999px;
          padding: 2px 8px;
          font-size: 11px;
          font-weight: 600;
        }
        .trd-badge.buy { color: #10b981; background: #dcfce7; }
        .trd-badge.sell { color: #ef4444; background: #fee2e2; }
        .trd-mono { font-family: var(--font-mono); }
        .trd-pos { color: #0f766e; }
        .trd-neg { color: #b91c1c; }

        .trd-skeleton-wrap { display: grid; gap: 8px; }
        .trd-skeleton {
          position: relative;
          overflow: hidden;
          background: #eef2f7;
          border-radius: 6px;
        }
        .trd-skeleton::after {
          content: '';
          position: absolute;
          inset: 0;
          transform: translateX(-100%);
          background: linear-gradient(90deg, transparent, rgba(255,255,255,0.7), transparent);
          animation: trd-shimmer 1.25s infinite;
        }
        .trd-skeleton-chart { height: 380px; }
        .trd-skeleton-line { height: 80px; }
        .trd-skeleton-row { height: 18px; margin: 4px 0; }
        @keyframes trd-shimmer {
          100% { transform: translateX(100%); }
        }

        @media (max-width: 1280px) {
          .trd-toolbar { grid-template-columns: 1fr; }
          .trd-main-grid { grid-template-columns: 1fr; }
          .trd-trade-pane { min-height: 300px; }
          .trd-kpi-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
          .trd-param-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        }
      `}</style>

      {error ? (
        <div style={{ border: '1px solid #fecaca', borderRadius: 10, padding: 10, color: '#dc2626', marginBottom: 12 }}>
          {error}
        </div>
      ) : null}

      {!priceOptions.length ? (
        <div style={{ border: '1px solid #e5e7eb', borderRadius: 10, padding: 10, color: '#64748b', marginBottom: 12 }}>
          No catalog data found. Fetch historical data from Backtest first.
        </div>
      ) : null}

      {modules.map((module) => (
        <DashboardModule
          key={module.id}
          module={module}
          onUpdate={updateModule}
          priceOptions={priceOptions}
          resultOptions={resultOptions}
          results={results}
          indicatorMeta={indicatorMeta}
          backtestMode={backtestMode}
          liveMode={liveMode}
        />
      ))}

      <div style={{ display: 'flex', justifyContent: 'center', marginTop: 8 }}>
        <button className="btn btn-primary" onClick={addModule}>
          Add Another Comparator
        </button>
      </div>

    </div>
  );
}
