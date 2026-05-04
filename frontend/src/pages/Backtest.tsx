import { useEffect, useMemo, useRef, useState } from 'react';
import CodeEditor from '../components/CodeEditor';
import {
  cancelHistoricalIngest,
  getBacktest,
  getBacktests,
  getCatalog,
  getHistoricalIngestJob,
  getStrategies,
  getStrategyClasses,
  getStrategyClassesById,
  getStrategySource,
  getStrategySourceById,
  runBacktest,
  saveStrategy,
  searchMapperInstruments,
  startHistoricalIngest,
  updateMapperInstruments,
} from '../services/api';
import { useBacktestStore } from '../stores/backtestStore';
import type {
  BacktestResult,
  CatalogEntry,
  HistoricalIngestJob,
  InstrumentSearchResult,
  Strategy,
} from '../types/backtest';

type DataSourceMode = 'mongodb' | 'zerodha_api';
type ControlSectionKey =
  | 'strategy_setup'
  | 'parameters'
  | 'risk_management'
  | 'ai_refiner'
  | 'execution_controls'
  | 'execute_strategy';

interface QueueItem {
  id: string;
  instrument_token: number;
  tradingsymbol: string;
  timeframe: string;
  date_from: string;
  date_to: string;
  source: string;
}

interface CatalogSelectionOption {
  id: string;
  instrument_token: number;
  tradingsymbol: string;
  timeframe: string;
  date_from: string;
  date_to: string;
  total_bars: number;
  source: string;
}

interface UnknownRecord {
  [key: string]: unknown;
}

interface BacktestSessionV2 {
  version: number;
  selectedStrategyId: string;
  strategyClassName: string;
  dataSourceMode: DataSourceMode;
  selectedMongoOptionId: string;
  instrumentToken: string;
  timeframe: string;
  dateFrom: string;
  dateTo: string;
  catalogQuery: string;
  symbolQuery: string;
  selectedSearchInstrument: InstrumentSearchResult | null;
  ingestInterval: string;
  ingestFrom: string;
  ingestTo: string;
  queueItems: QueueItem[];
  capital: string;
  commission: string;
  slippage: string;
  lotSize: string;
  positionSize: string;
  maxPositions: string;
  executionMode: string;
  maxRetries: string;
  taskTimeoutSeconds: string;
  enforceMarketHours: boolean;
  controlSectionsOpen: Record<ControlSectionKey, boolean>;
  activeIngestJobId: string;
  lastCompletedIngestSelectionId: string;
  executionLog: string[];
}

const INTERVAL_TO_TIMEFRAME: Record<string, string> = {
  minute: '1min',
  '3minute': '3min',
  '5minute': '5min',
  '10minute': '10min',
  '15minute': '15min',
  '30minute': '30min',
  '60minute': '60min',
  day: '1day',
};

const INGEST_INTERVALS = ['minute', '3minute', '5minute', '10minute', '15minute', '30minute', '60minute', 'day'];
const WORKSPACE_PANEL_HEIGHT = 760;
const CONTROL_RAIL_MIN_WIDTH = 340;
const QUEUE_SUBMIT_CONCURRENCY = 3;
const BACKTEST_SESSION_KEY = 'backtest-session-v2';
const BACKTEST_SESSION_VERSION = 2;
const TERMINAL_LOG_CAP = 500;
const EXECUTION_FIELD_HINTS: Record<string, string> = {
  initial_cash: 'Starting portfolio capital used by the backtest engine before the first order.',
  commission: 'Per-trade brokerage/fee rate applied to executed orders (for example 0.0003 = 0.03%).',
  slippage: 'Extra execution price impact applied on fills to simulate real market friction.',
  lot_size: 'Minimum tradable unit multiplier used when sizing orders.',
  position_size: 'Base units submitted per entry signal before other constraints are applied.',
  max_positions: 'Maximum simultaneous open positions allowed during execution.',
  execution_mode: 'Order fill assumption: market fills on signal execution, close fills at bar close.',
  max_retries: 'How many times the backend retries a failed run attempt before marking the task failed.',
  task_timeout: 'Maximum allowed runtime in seconds for one backtest task before timeout.',
};
const DEFAULT_CONTROL_SECTIONS: Record<ControlSectionKey, boolean> = {
  strategy_setup: true,
  parameters: true,
  risk_management: true,
  ai_refiner: true,
  execution_controls: true,
  execute_strategy: true,
};

const STRATEGY_TEMPLATE = `import backtrader as bt

class NewStrategy(bt.Strategy):
    def next(self):
        if not self.position:
            self.buy(size=1)
`;

function formatIst(value: string | null | undefined): string {
  if (!value) return '-';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(dt);
}

function parseToken(value: string): number | null {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? Math.trunc(n) : null;
}

function entrySource(entry: CatalogEntry): string {
  const values = new Set(
    (entry.timeframes_available || [])
      .map((tf) => String(tf.data_source || '').toLowerCase())
      .filter(Boolean),
  );
  if (!values.size) return 'historical';
  if (values.size > 1) return 'mixed';
  return values.values().next().value || 'historical';
}

function queueId(item: Omit<QueueItem, 'id'>): string {
  return `${item.instrument_token}|${item.timeframe}|${item.date_from}|${item.date_to}`;
}

function InfoIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.8" />
      <path d="M12 10.5V16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="12" cy="7.5" r="1" fill="currentColor" />
    </svg>
  );
}

function HintLabel({ label, hint }: { label: string; hint: string }) {
  return (
    <label className="stat-label backtest-hint-label">
      <span>{label}</span>
      <span className="backtest-hint-anchor" tabIndex={0} aria-label={`${label} help`}>
        <InfoIcon />
      </span>
      <span className="backtest-hint-tooltip" role="tooltip">{hint}</span>
    </label>
  );
}

function stemFromStrategy(strategy: Strategy | null): string {
  if (!strategy) return '';
  return strategy.name;
}

function canIngestInstrument(item: InstrumentSearchResult | null): boolean {
  if (!item) return false;
  const t = String(item.instrument_type || '').toUpperCase();
  const segment = String(item.segment || '').toUpperCase();
  if (segment === 'INDICES') return true;
  if (!t) return true;
  return ['EQ', 'INDEX', 'INDICES', 'ETF'].includes(t);
}

function instrumentCategory(item: InstrumentSearchResult): string {
  const segment = String(item.segment || '').toUpperCase();
  const instrumentType = String(item.instrument_type || '').toUpperCase();
  const symbol = String(item.tradingsymbol || '').toUpperCase();
  if (segment === 'INDICES' || instrumentType === 'INDEX' || symbol.includes('VIX')) return 'INDEX';
  if (instrumentType === 'CE' || instrumentType === 'PE') return instrumentType;
  if (instrumentType === 'FUT') return 'FUT';
  if (symbol.includes('ETF')) return 'ETF';
  if (instrumentType === 'EQ') return 'EQ';
  return instrumentType || segment || 'OTHER';
}

function normalizeSource(text: string): string {
  return text.replace(/\r\n/g, '\n');
}

function normalizeStrategyNameInput(value: string): string {
  const withoutExt = value.replace(/\.py$/i, '').trim();
  const flattened = withoutExt.replace(/\s+/g, '_');
  return flattened.replace(/[^A-Za-z0-9_-]/g, '_');
}

function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}

function parseIsoDate(value: string | undefined): Date | null {
  if (!value) return null;
  const dt = new Date(`${value}T00:00:00`);
  return Number.isNaN(dt.getTime()) ? null : dt;
}

function deriveIngestDateBounds(item: InstrumentSearchResult | null): { min: string; max: string } {
  const globalMin = '2015-02-01';
  const today = isoToday();
  if (!item) return { min: globalMin, max: today };

  const givenMin = item.available_from || '';
  const givenMax = item.available_to || '';
  if (givenMin && givenMax) {
    return { min: givenMin, max: givenMax < globalMin ? globalMin : givenMax };
  }

  const expiry = parseIsoDate(item.expiry);
  const todayDate = parseIsoDate(today)!;
  let maxDate = todayDate;
  if (expiry && expiry < maxDate) maxDate = expiry;
  const max = maxDate.toISOString().slice(0, 10);
  return { min: globalMin, max: max < globalMin ? globalMin : max };
}

function clampDate(value: string, min: string, max: string): string {
  if (!value) return '';
  if (value < min) return min;
  if (value > max) return max;
  return value;
}

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function normalizeCatalog(value: unknown): CatalogEntry[] {
  return asArray<UnknownRecord>(value).map((entry) => {
    const tokenValue = Number(entry.instrument_token);
    const instrument_token = Number.isFinite(tokenValue) ? tokenValue : 0;
    const tradingsymbolRaw = typeof entry.tradingsymbol === 'string' ? entry.tradingsymbol : '';
    const timeframesRaw = asArray<UnknownRecord>(entry.timeframes_available);
    const timeframes_available = timeframesRaw.map((tf) => ({
      timeframe: typeof tf.timeframe === 'string' ? tf.timeframe : '1day',
      date_from: typeof tf.date_from === 'string' ? tf.date_from : '',
      date_to: typeof tf.date_to === 'string' ? tf.date_to : '',
      total_bars: Number.isFinite(Number(tf.total_bars)) ? Number(tf.total_bars) : 0,
      data_source: typeof tf.data_source === 'string' ? tf.data_source : undefined,
    }));
    return {
      instrument_token,
      tradingsymbol: tradingsymbolRaw || String(instrument_token || ''),
      timeframes_available,
    };
  }).filter((entry) => Number.isFinite(entry.instrument_token));
}

function normalizeStrategies(value: unknown): Strategy[] {
  return asArray<UnknownRecord>(value).map((item) => ({
    name: typeof item.name === 'string' ? item.name : '',
    filename: typeof item.filename === 'string' ? item.filename : '',
    relative_path: typeof item.relative_path === 'string' ? item.relative_path : undefined,
    size_bytes: Number.isFinite(Number(item.size_bytes)) ? Number(item.size_bytes) : 0,
    immutable: Boolean(item.immutable),
  })).filter((s) => Boolean(s.name));
}

function normalizeResults(value: unknown): BacktestResult[] {
  return asArray<BacktestResult>(value);
}

function loadSessionSnapshot(): BacktestSessionV2 | null {
  try {
    if (typeof window === 'undefined' || !window.localStorage) return null;
    const raw = window.localStorage.getItem(BACKTEST_SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<BacktestSessionV2> | null;
    if (!parsed || typeof parsed !== 'object') return null;
    if (Number(parsed.version) !== BACKTEST_SESSION_VERSION) return null;
    return parsed as BacktestSessionV2;
  } catch {
    return null;
  }
}

function persistSessionSnapshot(snapshot: BacktestSessionV2): void {
  try {
    if (typeof window === 'undefined' || !window.localStorage) return;
    window.localStorage.setItem(BACKTEST_SESSION_KEY, JSON.stringify(snapshot));
  } catch {
    // Ignore localStorage failures.
  }
}

function mergeUniqueLines(existing: string[], incoming: string[]): string[] {
  if (!incoming.length) return existing.slice(-TERMINAL_LOG_CAP);
  const seen = new Set(existing);
  const next = [...existing];
  for (const line of incoming) {
    const normalized = String(line || '').trim();
    if (!normalized || seen.has(normalized)) continue;
    next.push(normalized);
    seen.add(normalized);
  }
  return next.slice(-TERMINAL_LOG_CAP);
}

function isTerminalIngestStatus(status: HistoricalIngestJob['status'] | string | undefined): boolean {
  const normalized = String(status || '').toUpperCase();
  return normalized === 'COMPLETED'
    || normalized === 'FAILED'
    || normalized === 'NO_DATA'
    || normalized === 'CANCELLED';
}

export default function BacktestPage() {
  const { strategies, catalog, setResults, setStrategies, setCatalog, updateResult } = useBacktestStore();
  const sessionSnapshotRef = useRef<BacktestSessionV2 | null>(null);
  if (sessionSnapshotRef.current === null) {
    sessionSnapshotRef.current = loadSessionSnapshot();
  }
  const sessionSnapshot = sessionSnapshotRef.current;

  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);
  const [executionLog, setExecutionLog] = useState<string[]>(
    () => asArray<string>(sessionSnapshot?.executionLog).slice(-TERMINAL_LOG_CAP),
  );
  const [runningTaskIds, setRunningTaskIds] = useState<string[]>([]);

  const [selectedStrategyId, setSelectedStrategyId] = useState<string>(sessionSnapshot?.selectedStrategyId || '');
  const [strategyName, setStrategyName] = useState('');
  const [strategyClassName, setStrategyClassName] = useState(sessionSnapshot?.strategyClassName || '');
  const [strategyClasses, setStrategyClasses] = useState<string[]>([]);
  const [strategySource, setStrategySource] = useState('');
  const [savedSource, setSavedSource] = useState('');
  const [editorLoading, setEditorLoading] = useState(false);
  const [editorSaving, setEditorSaving] = useState(false);
  const [versioningEnabled, setVersioningEnabled] = useState(false);
  const [newStrategyName, setNewStrategyName] = useState('');

  const [dataSourceMode, setDataSourceMode] = useState<DataSourceMode>(sessionSnapshot?.dataSourceMode || 'mongodb');
  const [catalogQuery, setCatalogQuery] = useState(sessionSnapshot?.catalogQuery || '');
  const [instrumentToken, setInstrumentToken] = useState(sessionSnapshot?.instrumentToken || '');
  const [timeframe, setTimeframe] = useState(sessionSnapshot?.timeframe || '1day');
  const [dateFrom, setDateFrom] = useState(sessionSnapshot?.dateFrom || '');
  const [dateTo, setDateTo] = useState(sessionSnapshot?.dateTo || '');
  const [selectedMongoOptionId, setSelectedMongoOptionId] = useState(sessionSnapshot?.selectedMongoOptionId || '');
  const [queueItems, setQueueItems] = useState<QueueItem[]>(() => asArray<QueueItem>(sessionSnapshot?.queueItems));

  const [capital, setCapital] = useState(sessionSnapshot?.capital || '100000');
  const [commission, setCommission] = useState(sessionSnapshot?.commission || '0.0003');
  const [slippage, setSlippage] = useState(sessionSnapshot?.slippage || '0');
  const [lotSize, setLotSize] = useState(sessionSnapshot?.lotSize || '1');
  const [positionSize, setPositionSize] = useState(sessionSnapshot?.positionSize || '1');
  const [maxPositions, setMaxPositions] = useState(sessionSnapshot?.maxPositions || '1');
  const [executionMode, setExecutionMode] = useState(sessionSnapshot?.executionMode || 'market');
  const [maxRetries, setMaxRetries] = useState(sessionSnapshot?.maxRetries || '0');
  const [taskTimeoutSeconds, setTaskTimeoutSeconds] = useState(sessionSnapshot?.taskTimeoutSeconds || '300');
  const [enforceMarketHours, setEnforceMarketHours] = useState(
    typeof sessionSnapshot?.enforceMarketHours === 'boolean' ? sessionSnapshot.enforceMarketHours : true,
  );
  const [queueSubmitting, setQueueSubmitting] = useState(false);

  const [symbolQuery, setSymbolQuery] = useState(sessionSnapshot?.symbolQuery || '');
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchWarning, setSearchWarning] = useState<string | null>(null);
  const [searchResults, setSearchResults] = useState<InstrumentSearchResult[]>([]);
  const [selectedSearchInstrument, setSelectedSearchInstrument] = useState<InstrumentSearchResult | null>(
    sessionSnapshot?.selectedSearchInstrument || null,
  );
  const [ingestInterval, setIngestInterval] = useState(sessionSnapshot?.ingestInterval || 'day');
  const [ingestFrom, setIngestFrom] = useState(sessionSnapshot?.ingestFrom || '');
  const [ingestTo, setIngestTo] = useState(sessionSnapshot?.ingestTo || '');
  const [ingestJob, setIngestJob] = useState<HistoricalIngestJob | null>(null);
  const [activeIngestJobId, setActiveIngestJobId] = useState(sessionSnapshot?.activeIngestJobId || '');
  const [lastCompletedIngestSelectionId, setLastCompletedIngestSelectionId] = useState(
    sessionSnapshot?.lastCompletedIngestSelectionId || '',
  );
  const [ingestStarting, setIngestStarting] = useState(false);
  const [ingestCancelling, setIngestCancelling] = useState(false);
  const [ingestPollError, setIngestPollError] = useState<string | null>(null);
  const [ingestStaleWarning, setIngestStaleWarning] = useState<string | null>(null);
  const [mapperUpdating, setMapperUpdating] = useState(false);
  const [controlSectionsOpen, setControlSectionsOpen] = useState<Record<ControlSectionKey, boolean>>(
    sessionSnapshot?.controlSectionsOpen || DEFAULT_CONTROL_SECTIONS,
  );
  const [clockNowMs, setClockNowMs] = useState<number>(() => Date.now());

  const wsRefs = useRef<Record<string, WebSocket>>({});
  const logCursor = useRef<Record<string, number>>({});
  const ingestChunkCursor = useRef<Record<string, number>>({});
  const ingestSavedRowsCursor = useRef<Record<string, number>>({});
  const ingestNoProgressPolls = useRef<Record<string, number>>({});
  const ingestProgressSignature = useRef<Record<string, string>>({});
  const ingestPollErrorCount = useRef<Record<string, number>>({});

  const appendTerminal = (line: string) => {
    setExecutionLog((prev) => mergeUniqueLines(prev, [line]));
  };

  const selectedCatalog = useMemo(() => {
    const token = parseToken(instrumentToken);
    if (token == null) return null;
    return catalog.find((entry) => entry.instrument_token === token) ?? null;
  }, [catalog, instrumentToken]);

  const selectedTfMeta = useMemo(
    () => selectedCatalog?.timeframes_available?.find((tf) => tf.timeframe === timeframe)
      ?? selectedCatalog?.timeframes_available?.[0]
      ?? null,
    [selectedCatalog, timeframe],
  );

  const filteredCatalog = useMemo(() => {
    const q = catalogQuery.trim().toUpperCase();
    return catalog.filter((entry) => {
      if (!q) return true;
      if (entry.tradingsymbol.toUpperCase().includes(q) || String(entry.instrument_token).includes(q)) return true;
      return (entry.timeframes_available || []).some((tf) => {
        const hay = `${tf.timeframe} ${tf.date_from} ${tf.date_to} ${tf.data_source || entrySource(entry)}`.toUpperCase();
        return hay.includes(q);
      });
    });
  }, [catalog, catalogQuery]);
  const catalogOptionsAll = useMemo<CatalogSelectionOption[]>(
    () => catalog.flatMap((entry) =>
      (entry.timeframes_available || []).map((tf) => ({
        id: `${entry.instrument_token}|${tf.timeframe}|${tf.date_from}|${tf.date_to}`,
        instrument_token: entry.instrument_token,
        tradingsymbol: entry.tradingsymbol,
        timeframe: tf.timeframe,
        date_from: tf.date_from,
        date_to: tf.date_to,
        total_bars: tf.total_bars,
        source: tf.data_source || entrySource(entry),
      }))),
    [catalog],
  );

  const mongoOptions = useMemo<CatalogSelectionOption[]>(
    () => filteredCatalog.flatMap((entry) =>
      (entry.timeframes_available || []).map((tf) => ({
        id: `${entry.instrument_token}|${tf.timeframe}|${tf.date_from}|${tf.date_to}`,
        instrument_token: entry.instrument_token,
        tradingsymbol: entry.tradingsymbol,
        timeframe: tf.timeframe,
        date_from: tf.date_from,
        date_to: tf.date_to,
        total_bars: tf.total_bars,
        source: tf.data_source || entrySource(entry),
      }))),
    [filteredCatalog],
  );

  const selectedMongoOption = useMemo(
    () => catalogOptionsAll.find((option) => option.id === selectedMongoOptionId) ?? null,
    [catalogOptionsAll, selectedMongoOptionId],
  );

  const timeframeOptions = useMemo(() => {
    const values = new Set((selectedCatalog?.timeframes_available || []).map((tf) => tf.timeframe));
    if (!values.size) values.add('1day');
    return Array.from(values);
  }, [selectedCatalog]);

  const editorDirty = normalizeSource(strategySource) !== normalizeSource(savedSource);
  const selectedStrategy = useMemo(
    () => strategies.find((s) => (s.relative_path || s.name) === selectedStrategyId) ?? null,
    [strategies, selectedStrategyId],
  );
  const selectedStrategyImmutable = Boolean(selectedStrategy?.immutable);
  const ingestStatusNormalized = String(ingestJob?.status || '').toUpperCase();
  const ingestIsBusy = ingestStatusNormalized === 'PENDING'
    || ingestStatusNormalized === 'RUNNING'
    || ingestStatusNormalized === 'CANCEL_REQUESTED';
  const ingestCanStop = ingestStatusNormalized === 'PENDING' || ingestStatusNormalized === 'RUNNING';

  const ingestDisabledReason = useMemo(() => {
    if (ingestStarting || ingestIsBusy) return 'Ingestion already in progress.';
    if (!selectedSearchInstrument) return 'Select one instrument from search results.';
    if (!canIngestInstrument(selectedSearchInstrument)) return `Unsupported instrument type: ${selectedSearchInstrument.instrument_type || 'unknown'}.`;
    if (!ingestFrom || !ingestTo) return 'Choose both from and to dates.';
    if (ingestFrom > ingestTo) return 'From date cannot be after To date.';
    return null;
  }, [ingestStarting, ingestIsBusy, selectedSearchInstrument, ingestFrom, ingestTo]);

  const ingestDateBounds = useMemo(
    () => deriveIngestDateBounds(selectedSearchInstrument),
    [selectedSearchInstrument],
  );
  const zerodhaQueueReady = dataSourceMode !== 'zerodha_api'
    || (Boolean(selectedMongoOptionId) && selectedMongoOptionId === lastCompletedIngestSelectionId);
  const ingestTiming = useMemo(() => {
    if (!ingestJob) return null;
    const startedMs = ingestJob.started_at ? Date.parse(ingestJob.started_at) : NaN;
    const startedValid = Number.isFinite(startedMs);
    const elapsedSec = startedValid ? Math.max(0, Math.floor((clockNowMs - startedMs) / 1000)) : null;
    const currentChunk = Number(ingestJob.current_chunk ?? 0);
    const totalChunks = Number(ingestJob.total_chunks ?? 0);
    const remainingChunks = totalChunks > currentChunk ? (totalChunks - currentChunk) : 0;
    let estimateMode: 'estimating' | 'ready' = 'estimating';
    let remainingSec: number | null = null;
    let estimatedFinishAt: string | null = null;

    const etaMs = ingestJob.estimated_finish_at ? Date.parse(ingestJob.estimated_finish_at) : NaN;
    if (Number.isFinite(etaMs)) {
      remainingSec = Math.max(0, Math.floor((etaMs - clockNowMs) / 1000));
      estimatedFinishAt = new Date(etaMs).toISOString();
      estimateMode = 'ready';
    } else if (elapsedSec != null && elapsedSec > 0 && currentChunk > 0 && totalChunks > currentChunk) {
      const avgSecPerChunk = elapsedSec / currentChunk;
      if (Number.isFinite(avgSecPerChunk) && avgSecPerChunk > 0) {
        remainingSec = Math.max(0, Math.floor(avgSecPerChunk * remainingChunks));
        estimatedFinishAt = new Date(clockNowMs + (remainingSec * 1000)).toISOString();
        estimateMode = 'ready';
      }
    }

    return {
      elapsedSec,
      remainingChunks,
      remainingSec,
      estimatedFinishAt,
      estimateMode,
    };
  }, [ingestJob, clockNowMs]);

  const connectTaskSocket = (taskId: string) => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/backtest/${taskId}`;
    wsRefs.current[taskId]?.close();
    const socket = new WebSocket(wsUrl);
    wsRefs.current[taskId] = socket;

    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data) as { type?: string; data?: BacktestResult };
        if (!message?.data || !message.data.task_id) return;
        const doc = message.data;
        updateResult(doc.task_id, doc);

        const lines = Array.isArray(doc.log_lines) ? doc.log_lines : [];
        const seen = logCursor.current[doc.task_id] ?? 0;
        if (lines.length > seen) {
          for (let i = seen; i < lines.length; i += 1) appendTerminal(lines[i]);
          logCursor.current[doc.task_id] = lines.length;
        }

        if (doc.status === 'COMPLETED' || doc.status === 'FAILED' || message.type === 'complete') {
          setRunningTaskIds((prev) => prev.filter((id) => id !== doc.task_id));
          // Final fetch guards against missing the last line during status transition.
          getBacktest(doc.task_id).then((full) => {
            const finalDoc = full as BacktestResult;
            updateResult(doc.task_id, finalDoc);
            const finalLines = Array.isArray(finalDoc.log_lines) ? finalDoc.log_lines : [];
            const seenFinal = logCursor.current[doc.task_id] ?? 0;
            for (let i = seenFinal; i < finalLines.length; i += 1) appendTerminal(finalLines[i]);
            logCursor.current[doc.task_id] = finalLines.length;
          }).catch(() => {});

          socket.close();
          delete wsRefs.current[doc.task_id];
        }
      } catch {
        // Ignore malformed messages.
      }
    };

    socket.onerror = () => {
      appendTerminal(`[${formatIst(new Date().toISOString())}] [WARN] WebSocket error for ${taskId}.`);
    };
  };

  const reloadCatalog = async () => {
    const fresh = await getCatalog();
    const nextCatalog = normalizeCatalog(fresh.catalog);
    setCatalog(nextCatalog);
    return nextCatalog;
  };

  const selectCatalogEntry = (entry: CatalogEntry, tf: CatalogEntry['timeframes_available'][number]) => {
    setInstrumentToken(String(entry.instrument_token));
    setTimeframe(tf.timeframe);
    setDateFrom(tf.date_from);
    setDateTo(tf.date_to);
    setSelectedMongoOptionId(`${entry.instrument_token}|${tf.timeframe}|${tf.date_from}|${tf.date_to}`);
  };

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      setLoading(true);
      setPageError(null);
      try {
        const [r, c, s] = await Promise.all([getBacktests(), getCatalog(), getStrategies()]);
        if (!mounted) return;
        const nextResults = normalizeResults(r.results);
        const nextCatalog = normalizeCatalog(c.catalog);
        const nextStrategies = normalizeStrategies(s.strategies);

        setResults(nextResults);
        setCatalog(nextCatalog);
        setStrategies(nextStrategies);

        const strategyCandidate = selectedStrategyId || sessionSnapshot?.selectedStrategyId || '';
        const matchedStrategy = nextStrategies.find((s) => (s.relative_path || s.name) === strategyCandidate) ?? null;
        if (matchedStrategy) {
          setSelectedStrategyId(matchedStrategy.relative_path || matchedStrategy.name);
          setStrategyName(stemFromStrategy(matchedStrategy));
        } else {
          const firstStrategy = nextStrategies[0] ?? null;
          if (firstStrategy) {
            setSelectedStrategyId(firstStrategy.relative_path || firstStrategy.name);
            setStrategyName(stemFromStrategy(firstStrategy));
            if (strategyCandidate) {
              appendTerminal(`[${formatIst(new Date().toISOString())}] [WARN] Previously selected strategy is unavailable. Loaded first available strategy.`);
            }
          }
        }

        const catalogOptionsAll = nextCatalog.flatMap((entry) =>
          (entry.timeframes_available || []).map((tf) => ({
            id: `${entry.instrument_token}|${tf.timeframe}|${tf.date_from}|${tf.date_to}`,
            entry,
            tf,
          })),
        );
        const mongoCandidate = selectedMongoOptionId || sessionSnapshot?.selectedMongoOptionId || '';
        if (mongoCandidate) {
          const matched = catalogOptionsAll.find((item) => item.id === mongoCandidate) ?? null;
          if (matched) {
            selectCatalogEntry(matched.entry, matched.tf);
          } else {
            setSelectedMongoOptionId('');
            setInstrumentToken('');
            setTimeframe('1day');
            setDateFrom('');
            setDateTo('');
            appendTerminal(`[${formatIst(new Date().toISOString())}] [WARN] Previously selected dataset is unavailable in refreshed catalog.`);
          }
        } else {
          const firstCatalog = nextCatalog[0] ?? null;
          if (firstCatalog) {
            const firstTf = firstCatalog.timeframes_available?.[0];
            if (firstTf) {
              selectCatalogEntry(firstCatalog, firstTf);
            }
          }
        }

        const jobIdToResume = (activeIngestJobId || sessionSnapshot?.activeIngestJobId || '').trim();
        if (jobIdToResume) {
          try {
            const doc = await getHistoricalIngestJob(jobIdToResume);
            if (!mounted) return;
            const job = doc as unknown as HistoricalIngestJob;
            setIngestJob(job);
            setActiveIngestJobId(isTerminalIngestStatus(job.status) ? '' : job.job_id);
            if (job.status === 'COMPLETED' && job.request) {
              const tf = INTERVAL_TO_TIMEFRAME[job.request.interval] || job.request.interval;
              const matched = nextCatalog.find((c) => c.instrument_token === job.request?.instrument_token);
              const matchedTf = matched?.timeframes_available?.find((x) => x.timeframe === tf)
                ?? matched?.timeframes_available?.[0];
              if (matched && matchedTf) {
                setLastCompletedIngestSelectionId(
                  `${matched.instrument_token}|${matchedTf.timeframe}|${matchedTf.date_from}|${matchedTf.date_to}`,
                );
              }
            }
            if (isTerminalIngestStatus(job.status)) {
              appendTerminal(
                `[${formatIst(new Date().toISOString())}] [INFO] Restored historical ingest job ${job.job_id} with terminal status ${job.status}.`,
              );
            } else {
              appendTerminal(
                `[${formatIst(new Date().toISOString())}] [INFO] Resumed tracking historical ingest job ${job.job_id}.`,
              );
            }
            const backendLines = asArray<string>(job.log_lines);
            if (backendLines.length) {
              setExecutionLog((prev) => mergeUniqueLines(prev, backendLines));
            }
          } catch (err: unknown) {
            if (!mounted) return;
            setActiveIngestJobId('');
            appendTerminal(
              `[${formatIst(new Date().toISOString())}] [WARN] Could not restore ingest job ${jobIdToResume}: ${err instanceof Error ? err.message : 'not found'}.`,
            );
          }
        }
      } catch (e: unknown) {
        if (!mounted) return;
        setPageError(e instanceof Error ? e.message : 'Failed to load backtest workspace');
      } finally {
        if (mounted) setLoading(false);
      }
    };
    load();
    return () => {
      mounted = false;
      Object.values(wsRefs.current).forEach((ws) => ws.close());
    };
  }, [setResults, setCatalog, setStrategies]);

  useEffect(() => {
    let mounted = true;
    if (!selectedStrategyId) return undefined;
    const loadStrategy = async () => {
      setEditorLoading(true);
      try {
        const strategy = strategies.find((s) => (s.relative_path || s.name) === selectedStrategyId) ?? null;
        const fallbackName = strategy?.name || '';
        const [src, classesResp] = await Promise.all([
          getStrategySourceById(selectedStrategyId, fallbackName),
          getStrategyClassesById(selectedStrategyId, fallbackName),
        ]);
        if (!mounted) return;
        setStrategyName(fallbackName);
        setStrategySource(src.source || '');
        setSavedSource(src.source || '');
        const classes = classesResp.classes || [];
        setStrategyClasses(classes);
        setStrategyClassName((prev) => (prev && classes.includes(prev) ? prev : (classes[0] || '')));
      } catch {
        try {
          const strategy = strategies.find((s) => (s.relative_path || s.name) === selectedStrategyId) ?? null;
          const legacyName = strategy?.name || '';
          if (!legacyName) throw new Error('Strategy not found');
          const [src, classesResp] = await Promise.all([
            getStrategySource(legacyName),
            getStrategyClasses(legacyName),
          ]);
          if (!mounted) return;
          setStrategyName(legacyName);
          setStrategySource(src.source || '');
          setSavedSource(src.source || '');
          const classes = classesResp.classes || [];
          setStrategyClasses(classes);
          setStrategyClassName((prev) => (prev && classes.includes(prev) ? prev : (classes[0] || '')));
        } catch (e: unknown) {
          if (!mounted) return;
          setPageError(e instanceof Error ? e.message : 'Failed to load strategy source');
        }
      } finally {
        if (mounted) setEditorLoading(false);
      }
    };
    loadStrategy();
    return () => {
      mounted = false;
    };
  }, [selectedStrategyId, strategies]);

  useEffect(() => {
    if (!selectedCatalog || !selectedTfMeta) return;
    if (!timeframeOptions.includes(timeframe)) setTimeframe(selectedTfMeta.timeframe);
    if (!dateFrom || dateFrom < selectedTfMeta.date_from || dateFrom > selectedTfMeta.date_to) setDateFrom(selectedTfMeta.date_from);
    if (!dateTo || dateTo < selectedTfMeta.date_from || dateTo > selectedTfMeta.date_to) setDateTo(selectedTfMeta.date_to);
  }, [selectedCatalog, selectedTfMeta, timeframeOptions, timeframe, dateFrom, dateTo]);

  useEffect(() => {
    if (dataSourceMode !== 'zerodha_api') {
      setSearchResults([]);
      setSearchWarning(null);
      return undefined;
    }
    if (symbolQuery.trim().length < 2) {
      setSearchResults([]);
      setSearchWarning(symbolQuery.trim().length ? 'Type at least 2 characters to search.' : null);
      return undefined;
    }
    let active = true;
    const timer = window.setTimeout(async () => {
      setSearchBusy(true);
      try {
        const data = await searchMapperInstruments(symbolQuery.trim(), 40);
        if (!active) return;
        const items = asArray<InstrumentSearchResult>(data.items);
        setSearchResults(items);
        setSearchWarning((data.warning as string | null) || null);
      } catch (e: unknown) {
        if (!active) return;
        setSearchWarning(e instanceof Error ? e.message : 'Search failed');
      } finally {
        if (active) setSearchBusy(false);
      }
    }, 300);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [symbolQuery, dataSourceMode]);

  useEffect(() => {
    if (dataSourceMode !== 'zerodha_api') return;
    const { min, max } = ingestDateBounds;
    setIngestFrom((prev) => {
      const next = clampDate(prev, min, max);
      if (!next) return min;
      return next;
    });
    setIngestTo((prev) => {
      const next = clampDate(prev, min, max);
      if (!next) return max;
      return next;
    });
  }, [ingestDateBounds, dataSourceMode]);

  useEffect(() => {
    const pollingJobId = (activeIngestJobId || ingestJob?.job_id || '').trim();
    if (!pollingJobId) return undefined;
    if (isTerminalIngestStatus(ingestJob?.status)) return undefined;
    let active = true;
    const timer = window.setInterval(async () => {
      try {
        const doc = await getHistoricalIngestJob(pollingJobId);
        if (!active) return;
        const job = doc as unknown as HistoricalIngestJob;
        setIngestPollError(null);
        ingestPollErrorCount.current[job.job_id] = 0;
        if (Array.isArray(job.log_lines) && job.log_lines.length) {
          setExecutionLog((prev) => mergeUniqueLines(prev, job.log_lines || []));
        }

        const signature = [
          job.status,
          job.phase || '',
          String(job.current_chunk ?? 0),
          String(job.rows_fetched ?? job.rows ?? 0),
          String(job.saved_rows ?? 0),
          String(job.inserted ?? 0),
        ].join('|');
        const prevSignature = ingestProgressSignature.current[job.job_id];
        if (prevSignature === signature) {
          ingestNoProgressPolls.current[job.job_id] = (ingestNoProgressPolls.current[job.job_id] ?? 0) + 1;
        } else {
          ingestProgressSignature.current[job.job_id] = signature;
          ingestNoProgressPolls.current[job.job_id] = 0;
          setIngestStaleWarning(null);
        }

        const chunkSeen = ingestChunkCursor.current[job.job_id] ?? 0;
        const chunkNow = Number(job.current_chunk ?? 0);
        const totalChunks = Number(job.total_chunks ?? 0);
        if (chunkNow > chunkSeen && totalChunks > 0) {
          ingestChunkCursor.current[job.job_id] = chunkNow;
          appendTerminal(
            `[${formatIst(new Date().toISOString())}] [INFO] Ingest ${job.job_id}: ${job.phase || 'RUNNING'} chunk ${chunkNow}/${totalChunks}, fetched=${job.rows_fetched ?? job.rows ?? 0}, saved=${job.saved_rows ?? 0}.`,
          );
        }
        const savedSeen = ingestSavedRowsCursor.current[job.job_id] ?? 0;
        const savedNow = Number(job.saved_rows ?? 0);
        if (savedNow > savedSeen) {
          ingestSavedRowsCursor.current[job.job_id] = savedNow;
          appendTerminal(
            `[${formatIst(new Date().toISOString())}] [INFO] Ingest ${job.job_id}: saved ${savedNow} rows (inserted ${job.inserted ?? 0}, modified ${job.modified ?? 0}).`,
          );
        }

        const noProgressCount = ingestNoProgressPolls.current[job.job_id] ?? 0;
        if ((job.status === 'RUNNING' || job.status === 'PENDING' || job.status === 'CANCEL_REQUESTED') && noProgressCount >= 5) {
          const warning = 'Ingest is still running but no progress has been reported recently.';
          setIngestStaleWarning(warning);
          if (noProgressCount === 5) appendTerminal(`[${formatIst(new Date().toISOString())}] [WARN] ${warning}`);
        }

        setIngestJob(job);
        if (isTerminalIngestStatus(job.status)) {
          setIngestStaleWarning(null);
          setActiveIngestJobId('');
          if (job.status === 'COMPLETED') {
            appendTerminal(
              `[${formatIst(new Date().toISOString())}] [SUCCESS] Historical ingest completed (fetched=${job.rows_fetched ?? job.rows ?? 0}, saved=${job.saved_rows ?? 0}, inserted=${job.inserted ?? 0}, modified=${job.modified ?? 0}).`,
            );
            const nextCatalog = await reloadCatalog();
            const request = job.request;
            if (request) {
              const tf = INTERVAL_TO_TIMEFRAME[request.interval] || request.interval;
              const matched = nextCatalog.find((c) => c.instrument_token === request.instrument_token);
              const matchedTf = matched?.timeframes_available?.find((x) => x.timeframe === tf)
                ?? matched?.timeframes_available?.[0];
              if (matched && matchedTf) {
                selectCatalogEntry(matched, matchedTf);
                setLastCompletedIngestSelectionId(
                  `${matched.instrument_token}|${matchedTf.timeframe}|${matchedTf.date_from}|${matchedTf.date_to}`,
                );
              }
            }
          } else if (job.status === 'NO_DATA') {
            appendTerminal(`[${formatIst(new Date().toISOString())}] [WARN] Historical ingest returned no candles.`);
          } else if (job.status === 'CANCELLED') {
            appendTerminal(`[${formatIst(new Date().toISOString())}] [WARN] Historical ingest cancelled and partial rows cleaned up.`);
          } else {
            appendTerminal(`[${formatIst(new Date().toISOString())}] [ERROR] Historical ingest failed: ${job.error_message || 'Unknown error'}`);
          }
        }
      } catch (e: unknown) {
        if (!active) return;
        const message = e instanceof Error ? e.message : 'Failed to poll ingest job status';
        setIngestPollError(message);
        const nextCount = (ingestPollErrorCount.current[pollingJobId] ?? 0) + 1;
        ingestPollErrorCount.current[pollingJobId] = nextCount;
        if (nextCount === 1 || nextCount % 3 === 0) {
          appendTerminal(`[${formatIst(new Date().toISOString())}] [WARN] Ingest polling issue: ${message}`);
        }
      }
    }, 2000);

    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [activeIngestJobId, ingestJob?.job_id, ingestJob?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const timer = window.setInterval(() => setClockNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const snapshot: BacktestSessionV2 = {
      version: BACKTEST_SESSION_VERSION,
      selectedStrategyId,
      strategyClassName,
      dataSourceMode,
      selectedMongoOptionId,
      instrumentToken,
      timeframe,
      dateFrom,
      dateTo,
      catalogQuery,
      symbolQuery,
      selectedSearchInstrument,
      ingestInterval,
      ingestFrom,
      ingestTo,
      queueItems,
      capital,
      commission,
      slippage,
      lotSize,
      positionSize,
      maxPositions,
      executionMode,
      maxRetries,
      taskTimeoutSeconds,
      enforceMarketHours,
      controlSectionsOpen,
      activeIngestJobId,
      lastCompletedIngestSelectionId,
      executionLog: executionLog.slice(-TERMINAL_LOG_CAP),
    };
    persistSessionSnapshot(snapshot);
  }, [
    selectedStrategyId,
    strategyClassName,
    dataSourceMode,
    selectedMongoOptionId,
    instrumentToken,
    timeframe,
    dateFrom,
    dateTo,
    catalogQuery,
    symbolQuery,
    selectedSearchInstrument,
    ingestInterval,
    ingestFrom,
    ingestTo,
    queueItems,
    capital,
    commission,
    slippage,
    lotSize,
    positionSize,
    maxPositions,
    executionMode,
    maxRetries,
    taskTimeoutSeconds,
    enforceMarketHours,
    controlSectionsOpen,
    activeIngestJobId,
    lastCompletedIngestSelectionId,
    executionLog,
  ]);

  const saveCurrentStrategy = async () => {
    if (selectedStrategyImmutable) {
      setPageError('Tutorial strategy is immutable. Create a new strategy file to edit and save.');
      return;
    }
    const normalizedName = normalizeStrategyNameInput(strategyName);
    if (!normalizedName) return;
    setEditorSaving(true);
    setPageError(null);
    try {
      const resp = await saveStrategy(normalizedName, strategySource, {
        strategy_id: selectedStrategyId || null,
        versioning_enabled: versioningEnabled,
      });
      setSavedSource(strategySource);
      const refreshed = await getStrategies();
      const next = normalizeStrategies(refreshed.strategies);
      setStrategies(next);

      const savedId = resp.strategy_id;
      if (savedId) {
        setSelectedStrategyId(savedId);
        const match = next.find((s) => (s.relative_path || s.name) === savedId) ?? null;
        if (match) setStrategyName(stemFromStrategy(match));
      }
      setVersioningEnabled(false);
      appendTerminal(`[${formatIst(new Date().toISOString())}] [SUCCESS] Saved strategy ${normalizedName}.`);
    } catch (e: unknown) {
      setPageError(e instanceof Error ? e.message : 'Failed to save strategy');
    } finally {
      setEditorSaving(false);
    }
  };

  const createNewStrategy = async () => {
    const name = normalizeStrategyNameInput(newStrategyName);
    if (!name) return;
    try {
      const className = name.replace(/[^a-zA-Z0-9_]/g, '_') || 'NewStrategy';
      const resp = await saveStrategy(name, STRATEGY_TEMPLATE.replace('NewStrategy', className), {
        strategy_id: null,
        versioning_enabled: false,
      });
      const refreshed = await getStrategies();
      const next = normalizeStrategies(refreshed.strategies);
      setStrategies(next);
      if (resp.strategy_id) setSelectedStrategyId(resp.strategy_id);
      setStrategyName(name);
      setNewStrategyName('');
      appendTerminal(`[${formatIst(new Date().toISOString())}] [SUCCESS] Created strategy ${name}.`);
    } catch (e: unknown) {
      setPageError(e instanceof Error ? e.message : 'Failed to create strategy');
    }
  };

  const currentSelection = (): Omit<QueueItem, 'id'> | null => {
    const token = parseToken(instrumentToken);
    if (token == null || !selectedCatalog) return null;
    const tfMeta = selectedCatalog.timeframes_available?.find((x) => x.timeframe === timeframe);
    const source = selectedMongoOption?.source || tfMeta?.data_source || entrySource(selectedCatalog);
    return {
      instrument_token: token,
      tradingsymbol: selectedCatalog.tradingsymbol,
      timeframe,
      date_from: dateFrom,
      date_to: dateTo,
      source,
    };
  };

  const addSelectionToQueue = () => {
    if (!zerodhaQueueReady) {
      setPageError('For Zerodha mode, wait for fetch completion and select the fetched MongoDB dataset before adding to queue.');
      return;
    }
    const selection = currentSelection();
    if (!selection) {
      setPageError('Select a valid instrument and timeframe.');
      return;
    }
    if (!dateFrom || !dateTo || dateFrom > dateTo) {
      setPageError('Provide a valid date range.');
      return;
    }
    const id = queueId(selection);
    setQueueItems((prev) => (prev.some((item) => item.id === id) ? prev : [...prev, { id, ...selection }]));
  };

  const submitRun = async (item: Omit<QueueItem, 'id'>) => {
    const resp = await runBacktest({
      strategy_name: strategyName.trim(),
      strategy_id: selectedStrategyId || null,
      strategy_class_name: strategyClassName || null,
      instrument_token: item.instrument_token,
      timeframe: item.timeframe,
      date_from: item.date_from,
      date_to: item.date_to,
      initial_capital: Number(capital),
      commission: Number(commission),
      slippage: Number(slippage),
      lot_size: Number(lotSize),
      position_size: Number(positionSize),
      max_positions: Number(maxPositions),
      execution_mode: executionMode,
      max_retries: Number(maxRetries),
      task_timeout_seconds: Number(taskTimeoutSeconds),
      enforce_market_hours: enforceMarketHours,
    });
    const taskId = resp.task_id;
    setRunningTaskIds((prev) => [...prev, taskId]);
    appendTerminal(
      `[${formatIst(new Date().toISOString())}] [INFO] Submitted ${item.tradingsymbol} (${item.timeframe}) as task ${taskId}.`,
    );
    connectTaskSocket(taskId);
  };

  const runNow = async () => {
    setPageError(null);
    if (!strategyName.trim()) {
      setPageError('Select a strategy file first.');
      return;
    }
    if (!strategyClassName.trim()) {
      setPageError('Select a strategy class.');
      return;
    }
    const selection = currentSelection();
    if (!selection) {
      setPageError('Select a valid instrument/timeframe.');
      return;
    }
    try {
      await submitRun(selection);
      const refreshed = await getBacktests();
      setResults(normalizeResults(refreshed.results));
    } catch (e: unknown) {
      setPageError(e instanceof Error ? e.message : 'Backtest submit failed');
    }
  };

  const handleRunQueue = async () => {
    if (!queueItems.length) {
      setPageError('Queue is empty.');
      return;
    }
    setQueueSubmitting(true);
    setPageError(null);
    try {
      const queueSnapshot = [...queueItems];
      let cursor = 0;
      const workers = Array.from(
        { length: Math.max(1, Math.min(QUEUE_SUBMIT_CONCURRENCY, queueSnapshot.length)) },
        async () => {
          while (cursor < queueSnapshot.length) {
            const index = cursor;
            cursor += 1;
            const { id: _id, ...requestItem } = queueSnapshot[index];
            await submitRun(requestItem);
          }
        },
      );
      await Promise.all(workers);
      setQueueItems([]);
      const refreshed = await getBacktests();
      setResults(normalizeResults(refreshed.results));
    } catch (e: unknown) {
      setPageError(e instanceof Error ? e.message : 'Queue submission failed');
    } finally {
      setQueueSubmitting(false);
    }
  };

  const startIngest = async () => {
    setPageError(null);
    setIngestPollError(null);
    setIngestStaleWarning(null);
    if (ingestDisabledReason) {
      setPageError(ingestDisabledReason);
      return;
    }
    if (!selectedSearchInstrument) return;

    setIngestStarting(true);
    try {
      setLastCompletedIngestSelectionId('');
      const resp = await startHistoricalIngest({
        instrument_token: selectedSearchInstrument.instrument_token,
        tradingsymbol: selectedSearchInstrument.tradingsymbol,
        from_date: ingestFrom,
        to_date: ingestTo,
        interval: ingestInterval,
      });
      setIngestJob({
        job_id: resp.job_id,
        status: resp.status as HistoricalIngestJob['status'],
        phase: 'PENDING',
        rows: 0,
        rows_fetched: 0,
        saved_rows: 0,
        inserted: 0,
        modified: 0,
        current_chunk: 0,
        total_chunks: 0,
        request: {
          instrument_token: selectedSearchInstrument.instrument_token,
          tradingsymbol: selectedSearchInstrument.tradingsymbol,
          from_date: ingestFrom,
          to_date: ingestTo,
          interval: ingestInterval,
        },
      });
      setActiveIngestJobId(resp.job_id);
      ingestChunkCursor.current[resp.job_id] = 0;
      ingestSavedRowsCursor.current[resp.job_id] = 0;
      ingestNoProgressPolls.current[resp.job_id] = 0;
      ingestProgressSignature.current[resp.job_id] = 'PENDING';
      ingestPollErrorCount.current[resp.job_id] = 0;
      appendTerminal(`[${formatIst(new Date().toISOString())}] [INFO] Started historical ingest job ${resp.job_id}.`);
    } catch (e: unknown) {
      setPageError(e instanceof Error ? e.message : 'Failed to start historical ingest');
    } finally {
      setIngestStarting(false);
    }
  };

  const stopIngest = async () => {
    if (!ingestJob?.job_id) return;
    if (!ingestCanStop) return;
    setIngestCancelling(true);
    try {
      await cancelHistoricalIngest(ingestJob.job_id);
      setIngestJob((prev) => (prev ? { ...prev, status: 'CANCEL_REQUESTED', phase: 'CANCEL_REQUESTED' } : prev));
      appendTerminal(`[${formatIst(new Date().toISOString())}] [WARN] Cancel requested for ingest job ${ingestJob.job_id}.`);
    } catch (e: unknown) {
      setPageError(e instanceof Error ? e.message : 'Failed to cancel historical ingest');
    } finally {
      setIngestCancelling(false);
    }
  };

  const refreshInstrumentMapper = async () => {
    setMapperUpdating(true);
    setPageError(null);
    try {
      const resp = await updateMapperInstruments();
      appendTerminal(
        `[${formatIst(new Date().toISOString())}] [SUCCESS] Instrument mapper updated. latest=${resp.rows_latest}, archive=${resp.rows_archive}.`,
      );
      if (symbolQuery.trim().length >= 2) {
        const data = await searchMapperInstruments(symbolQuery.trim(), 40);
        setSearchResults(asArray<InstrumentSearchResult>(data.items));
        setSearchWarning((data.warning as string | null) || null);
      }
    } catch (e: unknown) {
      setPageError(e instanceof Error ? e.message : 'Failed to update instrument mapper');
    } finally {
      setMapperUpdating(false);
    }
  };

  const requestStrategySwitch = (nextId: string) => {
    if (!nextId || nextId === selectedStrategyId) return;
    if (editorDirty) {
      const ok = window.confirm('You have unsaved strategy edits. Switch strategy and discard unsaved changes?');
      if (!ok) return;
    }
    setSelectedStrategyId(nextId);
    const strategy = strategies.find((s) => (s.relative_path || s.name) === nextId) ?? null;
    setStrategyName(stemFromStrategy(strategy));
  };

  const clearMongoSelection = () => {
    setSelectedMongoOptionId('');
    setInstrumentToken('');
    setTimeframe('1day');
    setDateFrom('');
    setDateTo('');
  };

  const setAllControlSections = (open: boolean) => {
    setControlSectionsOpen({
      ...DEFAULT_CONTROL_SECTIONS,
      strategy_setup: open,
      parameters: open,
      risk_management: open,
      ai_refiner: open,
      execution_controls: open,
      execute_strategy: open,
    });
  };

  const handleControlSectionToggle = (key: ControlSectionKey, open: boolean) => {
    setControlSectionsOpen((prev) => ({ ...prev, [key]: open }));
  };

  return (
    <div className="animate-in backtest-page">
      {pageError ? (
        <div className="card" style={{ marginBottom: 'var(--space-lg)', borderColor: 'var(--red-dim)', color: 'var(--red)' }}>
          {pageError}
        </div>
      ) : null}

      <div className="backtest-workspace-grid">
        <div className="card backtest-panel backtest-editor-card" style={{ height: WORKSPACE_PANEL_HEIGHT, display: 'flex', flexDirection: 'column' }}>
          <div className="card-header backtest-panel-header">
            <span className="card-title">Strategy Workspace</span>
            <div className="backtest-editor-actions">
              <input
                className="input backtest-inline-input"
                placeholder="new_strategy_name"
                value={newStrategyName}
                onChange={(e) => setNewStrategyName(e.target.value)}
              />
              <button className="btn btn-topnav btn-sm" disabled={!normalizeStrategyNameInput(newStrategyName)} onClick={createNewStrategy}>
                Create Strategy
              </button>
              {selectedStrategyImmutable ? (
                <span className="badge badge-neutral">Immutable Tutorial</span>
              ) : null}
              <span className={`badge ${editorDirty ? 'badge-warning' : 'badge-success'}`}>{editorDirty ? 'Dirty' : 'Saved'}</span>
              <button className="btn btn-topnav btn-sm" disabled={!editorDirty || editorSaving || selectedStrategyImmutable} onClick={() => setStrategySource(savedSource)}>Revert</button>
              <button className="btn btn-topnav btn-sm" disabled={!editorDirty || editorSaving || selectedStrategyImmutable} onClick={saveCurrentStrategy}>
                {editorSaving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>

          <div className="grid grid-2 backtest-form-grid">
            <div className="backtest-field">
              <label className="stat-label">Strategy File</label>
              <select
                value={selectedStrategyId}
                onChange={(e) => {
                  requestStrategySwitch(e.target.value);
                }}
              >
                <option value="">Select strategy...</option>
                {strategies.map((s) => {
                  const id = s.relative_path || s.name;
                  return (
                    <option key={id} value={id}>
                      {s.name}{s.immutable ? ' [IMMUTABLE]' : ''} ({id})
                    </option>
                  );
                })}
              </select>
            </div>
            <div className="backtest-field">
              <label className="stat-label">Strategy Class</label>
              <select value={strategyClassName} onChange={(e) => setStrategyClassName(e.target.value)}>
                <option value="">Select class...</option>
                {strategyClasses.map((cls) => (
                  <option key={cls} value={cls}>{cls}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="backtest-field backtest-save-name">
            <label className="stat-label">Save Name</label>
            <input className="input" value={strategyName} onChange={(e) => setStrategyName(e.target.value)} disabled={selectedStrategyImmutable} />
            {selectedStrategyImmutable ? (
              <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: 6 }}>
                This tutorial strategy is read-only. Duplicate it to create your own editable strategy.
              </div>
            ) : null}
          </div>

          <div className="backtest-editor-host" style={{ flex: 1, minHeight: 0 }}>
            {editorLoading ? (
              <div style={{ color: 'var(--text-muted)' }}>Loading strategy source...</div>
            ) : (
              <CodeEditor value={strategySource} onChange={setStrategySource} height="100%" readOnly={selectedStrategyImmutable} />
            )}
          </div>

        </div>

        <div className="card backtest-panel backtest-control-card" style={{ height: WORKSPACE_PANEL_HEIGHT, minWidth: CONTROL_RAIL_MIN_WIDTH, display: 'flex', flexDirection: 'column' }}>
          <div className="card-header backtest-panel-header backtest-control-header">
            <span className="card-title">Control Rail</span>
            <div className="backtest-control-header-actions">
              <button type="button" className="btn btn-topnav btn-sm" onClick={() => setAllControlSections(true)}>Expand All</button>
              <button type="button" className="btn btn-topnav btn-sm" onClick={() => setAllControlSections(false)}>Collapse All</button>
            </div>
          </div>
          <div className="backtest-control-scroll">

          <details
            open={controlSectionsOpen.strategy_setup}
            onToggle={(e) => {
              const isOpen = (e.currentTarget as HTMLDetailsElement).open;
              handleControlSectionToggle('strategy_setup', isOpen);
            }}
            className="backtest-section"
          >
            <summary className="backtest-section-title backtest-section-title-nav">Strategy Setup</summary>
            <div className="backtest-section-body">
              <label className="stat-label">Source Mode</label>
              <select value={dataSourceMode} onChange={(e) => setDataSourceMode(e.target.value as DataSourceMode)}>
                <option value="mongodb">MongoDB</option>
                <option value="zerodha_api">Zerodha API Data</option>
              </select>

              {dataSourceMode === 'mongodb' ? (
                <>
                  <label className="stat-label">Search Stored Datasets</label>
                  <input
                    className="input"
                    placeholder="Search by symbol, token, timeframe, date range, source"
                    value={catalogQuery}
                    onChange={(e) => setCatalogQuery(e.target.value)}
                  />

                  {!catalog.length ? (
                    <div style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>
                      Catalog is empty. Switch to Zerodha API Data mode and fetch bars first.
                    </div>
                  ) : null}

                  {selectedMongoOption ? (
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)', borderRadius: 8, padding: 8 }}>
                      <b>Selected:</b> {selectedMongoOption.tradingsymbol} | token {selectedMongoOption.instrument_token} | {selectedMongoOption.timeframe} | {selectedMongoOption.date_from} to {selectedMongoOption.date_to} | {selectedMongoOption.source}
                      <button className="btn btn-topnav btn-sm" style={{ marginLeft: 8 }} onClick={clearMongoSelection}>Clear</button>
                    </div>
                  ) : (
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                      No MongoDB dataset selected yet.
                    </div>
                  )}

                  <div style={{ maxHeight: 200, overflowY: 'auto', border: '1px solid var(--border-subtle)', borderRadius: 8, padding: 6, display: 'grid', gap: 6 }}>
                    {mongoOptions.length ? mongoOptions.map((option) => (
                      <button
                        key={option.id}
                        type="button"
                        className="btn btn-dropdown btn-sm"
                        style={{
                          justifyContent: 'flex-start',
                          textAlign: 'left',
                          background: option.id === selectedMongoOptionId ? 'rgba(37,99,235,0.16)' : undefined,
                        }}
                        onMouseDown={() => {
                          const entry = catalog.find((x) => x.instrument_token === option.instrument_token) ?? null;
                          const tf = entry?.timeframes_available?.find((x) =>
                            x.timeframe === option.timeframe && x.date_from === option.date_from && x.date_to === option.date_to);
                          if (entry && tf) selectCatalogEntry(entry, tf);
                        }}
                      >
                        {option.tradingsymbol} | {option.instrument_token} | {option.timeframe} | {option.date_from} to {option.date_to} | bars {Number(option.total_bars || 0).toLocaleString()} | {option.source}
                      </button>
                    )) : (
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>No matching datasets.</div>
                    )}
                  </div>
                  <label className="stat-label">Timeframe</label>
                  <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
                    {timeframeOptions.map((tf) => <option key={tf} value={tf}>{tf}</option>)}
                  </select>
                  <label className="stat-label">Date Range</label>
                  <div className="grid grid-2 backtest-form-grid">
                    <input className="input" type="date" value={dateFrom} min={selectedTfMeta?.date_from} max={selectedTfMeta?.date_to} onChange={(e) => setDateFrom(e.target.value)} />
                    <input className="input" type="date" value={dateTo} min={selectedTfMeta?.date_from} max={selectedTfMeta?.date_to} onChange={(e) => setDateTo(e.target.value)} />
                  </div>
                  <button
                    className="btn btn-topnav btn-sm"
                    disabled={!selectedMongoOption}
                    onClick={addSelectionToQueue}
                  >
                    Add to Queue
                  </button>
                </>
              ) : (
                <>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                    Instrument search uses mapper files: <code>zerodha_instruments_latest.csv</code> + <code>zerodha_instruments_archive.csv</code>.
                  </div>
                  <label className="stat-label">Search Zerodha Instrument</label>
                  <div className="backtest-inline-row">
                    <input
                      className="input"
                      placeholder="Search symbol (e.g. RELIANCE)"
                      value={symbolQuery}
                      onChange={(e) => setSymbolQuery(e.target.value)}
                    />
                    <button className="btn btn-topnav btn-sm" disabled={mapperUpdating} onClick={refreshInstrumentMapper}>
                      {mapperUpdating ? 'Updating...' : 'Update Mapper'}
                    </button>
                  </div>
                  {searchBusy ? <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>Searching instruments...</div> : null}
                  {searchWarning ? <div style={{ color: 'var(--amber)', fontSize: '0.8rem' }}>{searchWarning}</div> : null}

                  {selectedSearchInstrument ? (
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)', borderRadius: 8, padding: 8 }}>
                      <b>Selected:</b> {selectedSearchInstrument.tradingsymbol} | token {selectedSearchInstrument.instrument_token} | {selectedSearchInstrument.exchange || '-'} | {selectedSearchInstrument.segment || '-'} | {selectedSearchInstrument.instrument_type || '-'} | {instrumentCategory(selectedSearchInstrument)}
                      <button className="btn btn-topnav btn-sm" style={{ marginLeft: 8 }} onClick={() => setSelectedSearchInstrument(null)}>Clear</button>
                      {instrumentCategory(selectedSearchInstrument) === 'INDEX' ? (
                        <div style={{ marginTop: 6, color: 'var(--accent)', fontWeight: 600 }}>Index instrument selected</div>
                      ) : null}
                    </div>
                  ) : null}

                  <div style={{ maxHeight: 170, overflowY: 'auto', border: '1px solid var(--border-subtle)', borderRadius: 8, padding: 6, display: 'grid', gap: 6 }}>
                    {searchResults.length ? searchResults.map((item) => (
                      <button
                        key={`${item.instrument_token}-${item.tradingsymbol}-${item.segment || ''}-${item.expiry || ''}-${item.strike || ''}`}
                        type="button"
                        className="btn btn-dropdown btn-sm"
                        style={{
                          justifyContent: 'flex-start',
                          textAlign: 'left',
                          background: selectedSearchInstrument?.instrument_token === item.instrument_token ? 'rgba(37,99,235,0.16)' : undefined,
                        }}
                        onMouseDown={() => {
                          setSelectedSearchInstrument(item);
                          if (!symbolQuery.trim()) setSymbolQuery(item.tradingsymbol);
                        }}
                      >
                        {item.tradingsymbol} | {item.instrument_token} | {item.exchange || '-'} | {item.segment || '-'} | {item.instrument_type || '-'} | {instrumentCategory(item)} {item.expiry ? `| exp ${item.expiry}` : ''}
                      </button>
                    )) : (
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>No matches</div>
                    )}
                  </div>

                  <label className="stat-label">Interval</label>
                  <select value={ingestInterval} onChange={(e) => setIngestInterval(e.target.value)}>
                    {INGEST_INTERVALS.map((it) => <option key={it} value={it}>{it}</option>)}
                  </select>
                  <label className="stat-label">Fetch Date Range</label>
                  <div className="grid grid-2 backtest-form-grid">
                    <input
                      className="input"
                      type="date"
                      min={ingestDateBounds.min}
                      max={ingestDateBounds.max}
                      value={ingestFrom}
                      onChange={(e) => setIngestFrom(e.target.value)}
                    />
                    <input
                      className="input"
                      type="date"
                      min={ingestDateBounds.min}
                      max={ingestDateBounds.max}
                      value={ingestTo}
                      onChange={(e) => setIngestTo(e.target.value)}
                    />
                  </div>
                  <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)' }}>
                    Available range for selected instrument: {ingestDateBounds.min} to {ingestDateBounds.max}
                  </div>
                  <div className="backtest-inline-row">
                    <button
                      className="btn btn-topnav btn-sm"
                      disabled={Boolean(ingestDisabledReason)}
                      onClick={startIngest}
                    >
                      {ingestStarting ? 'Starting...' : 'Fetch to MongoDB'}
                    </button>
                    <button
                      className="btn btn-danger btn-sm"
                      disabled={!ingestCanStop || ingestCancelling}
                      onClick={stopIngest}
                    >
                      {ingestCancelling ? 'Stopping...' : 'Stop'}
                    </button>
                  </div>
                  {ingestDisabledReason ? <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{ingestDisabledReason}</div> : null}
                  <button
                    className="btn btn-topnav btn-sm"
                    disabled={!selectedMongoOption || !zerodhaQueueReady}
                    onClick={addSelectionToQueue}
                  >
                    Add to Queue
                  </button>
                  {!zerodhaQueueReady ? (
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                      Add to Queue is enabled after this fetch completes and the fetched MongoDB dataset is selected.
                    </div>
                  ) : null}
                  {ingestJob ? (
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                      Job {ingestJob.job_id}: <b>{ingestJob.status}</b> ({ingestJob.phase || 'RUNNING'})
                      {' | '}chunk={ingestJob.current_chunk ?? 0}/{ingestJob.total_chunks ?? 0}
                      {' | '}fetched={ingestJob.rows_fetched ?? ingestJob.rows ?? 0}
                      {' | '}saved={ingestJob.saved_rows ?? 0}
                      {' | '}inserted={ingestJob.inserted ?? 0}
                      {' | '}modified={ingestJob.modified ?? 0}
                      {ingestJob.error_message ? ` | ${ingestJob.error_message}` : ''}
                    </div>
                  ) : null}
                  {ingestJob ? (
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                      Elapsed: {ingestTiming?.elapsedSec != null ? `${ingestTiming.elapsedSec}s` : 'Estimating...'}
                      {' | '}Remaining chunks: {ingestTiming?.remainingChunks ?? 0}
                      {' | '}ETA: {ingestTiming?.estimateMode === 'ready' && ingestTiming.estimatedFinishAt ? formatIst(ingestTiming.estimatedFinishAt) : 'Estimating...'}
                      {' | '}Countdown: {ingestTiming?.estimateMode === 'ready' && ingestTiming.remainingSec != null ? `${ingestTiming.remainingSec}s` : 'Estimating...'}
                    </div>
                  ) : null}
                  {ingestStaleWarning ? (
                    <div style={{ fontSize: '0.78rem', color: 'var(--amber)' }}>{ingestStaleWarning}</div>
                  ) : null}
                  {ingestPollError ? (
                    <div style={{ fontSize: '0.78rem', color: '#ef4444' }}>Polling issue: {ingestPollError}</div>
                  ) : null}
                </>
              )}
            </div>
          </details>

          <details
            open={controlSectionsOpen.parameters}
            onToggle={(e) => {
              const isOpen = (e.currentTarget as HTMLDetailsElement).open;
              handleControlSectionToggle('parameters', isOpen);
            }}
            className="backtest-section"
          >
            <summary className="backtest-section-title backtest-section-title-nav">Parameters</summary>
            <div className="backtest-section-body">
              <label className="stat-label">Selected Strategy ID</label>
              <input className="input" value={selectedStrategyId || '-'} readOnly />
              <label className="stat-label">Rename / Save Name</label>
              <input className="input" value={strategyName} onChange={(e) => setStrategyName(e.target.value)} disabled={selectedStrategyImmutable} />
              <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                Saving uses safe rename rules and path-stable <code>strategy_id</code> resolution.
              </div>
            </div>
          </details>

          <details
            open={controlSectionsOpen.risk_management}
            onToggle={(e) => {
              const isOpen = (e.currentTarget as HTMLDetailsElement).open;
              handleControlSectionToggle('risk_management', isOpen);
            }}
            className="backtest-section"
          >
            <summary className="backtest-section-title backtest-section-title-nav">Risk Management</summary>
            <label className="backtest-check">
              <input type="checkbox" checked={versioningEnabled} onChange={(e) => setVersioningEnabled(e.target.checked)} />
              Save as versioned file (backend-driven)
            </label>
          </details>

          <details
            open={controlSectionsOpen.ai_refiner}
            onToggle={(e) => {
              const isOpen = (e.currentTarget as HTMLDetailsElement).open;
              handleControlSectionToggle('ai_refiner', isOpen);
            }}
            className="backtest-section"
          >
            <summary className="backtest-section-title backtest-section-title-nav">AI Powered Strategy Refiner</summary>
            <div style={{ color: 'var(--text-muted)', fontSize: '0.82rem', marginBottom: 12 }}>
              Placeholder section kept for old workspace parity. Hook your refiner endpoint here.
            </div>
          </details>

          <details
            open={controlSectionsOpen.execution_controls}
            onToggle={(e) => {
              const isOpen = (e.currentTarget as HTMLDetailsElement).open;
              handleControlSectionToggle('execution_controls', isOpen);
            }}
            className="backtest-section"
          >
            <summary className="backtest-section-title backtest-section-title-nav">Execution Controls</summary>
            <div className="backtest-section-body">
              <HintLabel label="Initial Cash" hint={EXECUTION_FIELD_HINTS.initial_cash} />
              <input className="input" type="number" min={1} value={capital} onChange={(e) => setCapital(e.target.value)} />
              <HintLabel label="Commission" hint={EXECUTION_FIELD_HINTS.commission} />
              <input className="input" type="number" step="0.0001" min={0} value={commission} onChange={(e) => setCommission(e.target.value)} />
              <HintLabel label="Slippage" hint={EXECUTION_FIELD_HINTS.slippage} />
              <input className="input" type="number" step="0.0001" min={0} value={slippage} onChange={(e) => setSlippage(e.target.value)} />
              <div className="grid grid-2 backtest-form-grid">
                <div>
                  <HintLabel label="Lot Size" hint={EXECUTION_FIELD_HINTS.lot_size} />
                  <input className="input" type="number" min={1} value={lotSize} onChange={(e) => setLotSize(e.target.value)} />
                </div>
                <div>
                  <HintLabel label="Position Size" hint={EXECUTION_FIELD_HINTS.position_size} />
                  <input className="input" type="number" min={1} value={positionSize} onChange={(e) => setPositionSize(e.target.value)} />
                </div>
              </div>
              <div className="grid grid-2 backtest-form-grid">
                <div>
                  <HintLabel label="Max Positions" hint={EXECUTION_FIELD_HINTS.max_positions} />
                  <input className="input" type="number" min={1} value={maxPositions} onChange={(e) => setMaxPositions(e.target.value)} />
                </div>
                <div>
                  <HintLabel label="Execution Mode" hint={EXECUTION_FIELD_HINTS.execution_mode} />
                  <select value={executionMode} onChange={(e) => setExecutionMode(e.target.value)}>
                    <option value="market">market</option>
                    <option value="close">close</option>
                  </select>
                </div>
              </div>
              <div className="grid grid-2 backtest-form-grid">
                <div>
                  <HintLabel label="Max Retries" hint={EXECUTION_FIELD_HINTS.max_retries} />
                  <input className="input" type="number" min={0} value={maxRetries} onChange={(e) => setMaxRetries(e.target.value)} />
                </div>
                <div>
                  <HintLabel label="Task Timeout (s)" hint={EXECUTION_FIELD_HINTS.task_timeout} />
                  <input className="input" type="number" min={10} value={taskTimeoutSeconds} onChange={(e) => setTaskTimeoutSeconds(e.target.value)} />
                </div>
              </div>
              <label className="backtest-check">
                <input type="checkbox" checked={enforceMarketHours} onChange={(e) => setEnforceMarketHours(e.target.checked)} />
                Enforce market hours
              </label>
            </div>
          </details>

          <details
            open={controlSectionsOpen.execute_strategy}
            onToggle={(e) => {
              const isOpen = (e.currentTarget as HTMLDetailsElement).open;
              handleControlSectionToggle('execute_strategy', isOpen);
            }}
            className="backtest-section"
          >
            <summary className="backtest-section-title backtest-section-title-nav">Execute Strategy</summary>
            <div className="backtest-button-row">
              <button className="btn btn-topnav btn-sm" onClick={runNow} disabled={loading || !!runningTaskIds.length}>Run Now</button>
              <button className="btn btn-topnav btn-sm" onClick={handleRunQueue} disabled={queueSubmitting || !queueItems.length || !!runningTaskIds.length}>
                {queueSubmitting ? 'Running...' : `Run Queue (${queueItems.length})`}
              </button>
              <button className="btn btn-topnav btn-sm" onClick={() => setQueueItems([])} disabled={!queueItems.length || queueSubmitting}>
                Clear Queue
              </button>
            </div>
            <div className="table-wrapper backtest-queue-table">
              <table>
                <thead><tr><th>Symbol</th><th>TF</th><th>Range</th><th /></tr></thead>
                <tbody>
                  {queueItems.map((item) => (
                    <tr key={item.id}>
                      <td>{item.tradingsymbol}</td>
                      <td>{item.timeframe}</td>
                      <td style={{ fontSize: '0.76rem' }}>{item.date_from} to {item.date_to}</td>
                      <td style={{ textAlign: 'right' }}>
                        <button
                          className="btn btn-topnav btn-sm"
                          onClick={() => setQueueItems((prev) => prev.filter((x) => x.id !== item.id))}
                          disabled={queueSubmitting}
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))}
                  {!queueItems.length ? <tr><td colSpan={4} style={{ textAlign: 'center' }}>Queue empty</td></tr> : null}
                </tbody>
              </table>
            </div>
          </details>

          </div>
        </div>
      </div>

      <div className="backtest-primary-actions">
        <button className="btn btn-primary" disabled={loading || !!runningTaskIds.length} onClick={runNow}>Run Backtest</button>
        <button className="btn btn-topnav" disabled={!editorDirty || editorSaving || selectedStrategyImmutable} onClick={saveCurrentStrategy}>
          {editorSaving ? 'Saving...' : 'Save Strategy'}
        </button>
        <button className="btn btn-ghost" disabled={!editorDirty || editorSaving || selectedStrategyImmutable} onClick={() => setStrategySource(savedSource)}>
          Reset
        </button>
      </div>

      <div className="card backtest-terminal-card" style={{ marginBottom: 'var(--space-xl)' }}>
        <div className="card-header">
          <span className="card-title">Execution Terminal</span>
          <div className="backtest-inline-row">
            <span className={`badge ${runningTaskIds.length ? 'badge-warning' : 'badge-success'}`}>
              {runningTaskIds.length ? `Running ${runningTaskIds.length}` : 'Idle'}
            </span>
            <button className="btn btn-ghost btn-sm" onClick={() => setExecutionLog([])}>Clear</button>
          </div>
        </div>
        <div className="backtest-terminal-body">
          {executionLog.length ? executionLog.slice().reverse().map((line, idx) => (
            <div key={`${line}-${idx}`} className="backtest-terminal-line">{line}</div>
          )) : (
            <div style={{ color: 'var(--text-muted)' }}>
              {loading ? 'Loading workspace...' : 'No execution logs yet.'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
