import { useEffect, useMemo, useRef, useState } from 'react';
import CodeEditor from '../components/CodeEditor';
import PageMetaBar from '../components/PageMetaBar';
import {
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

export default function BacktestPage() {
  const { strategies, catalog, setResults, setStrategies, setCatalog, updateResult } = useBacktestStore();

  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);
  const [executionLog, setExecutionLog] = useState<string[]>([]);
  const [runningTaskIds, setRunningTaskIds] = useState<string[]>([]);

  const [selectedStrategyId, setSelectedStrategyId] = useState<string>('');
  const [strategyName, setStrategyName] = useState('');
  const [strategyClassName, setStrategyClassName] = useState('');
  const [strategyClasses, setStrategyClasses] = useState<string[]>([]);
  const [strategySource, setStrategySource] = useState('');
  const [savedSource, setSavedSource] = useState('');
  const [editorLoading, setEditorLoading] = useState(false);
  const [editorSaving, setEditorSaving] = useState(false);
  const [versioningEnabled, setVersioningEnabled] = useState(false);
  const [newStrategyName, setNewStrategyName] = useState('');

  const [dataSourceMode, setDataSourceMode] = useState<DataSourceMode>('mongodb');
  const [catalogQuery, setCatalogQuery] = useState('');
  const [instrumentToken, setInstrumentToken] = useState('');
  const [timeframe, setTimeframe] = useState('1day');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [selectedMongoOptionId, setSelectedMongoOptionId] = useState('');
  const [queueItems, setQueueItems] = useState<QueueItem[]>([]);

  const [capital, setCapital] = useState('100000');
  const [commission, setCommission] = useState('0.0003');
  const [slippage, setSlippage] = useState('0');
  const [lotSize, setLotSize] = useState('1');
  const [positionSize, setPositionSize] = useState('1');
  const [maxPositions, setMaxPositions] = useState('1');
  const [executionMode, setExecutionMode] = useState('market');
  const [maxRetries, setMaxRetries] = useState('0');
  const [taskTimeoutSeconds, setTaskTimeoutSeconds] = useState('300');
  const [enforceMarketHours, setEnforceMarketHours] = useState(true);
  const [queueSubmitting, setQueueSubmitting] = useState(false);

  const [symbolQuery, setSymbolQuery] = useState('');
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchWarning, setSearchWarning] = useState<string | null>(null);
  const [searchResults, setSearchResults] = useState<InstrumentSearchResult[]>([]);
  const [selectedSearchInstrument, setSelectedSearchInstrument] = useState<InstrumentSearchResult | null>(null);
  const [ingestInterval, setIngestInterval] = useState('day');
  const [ingestFrom, setIngestFrom] = useState('');
  const [ingestTo, setIngestTo] = useState('');
  const [ingestJob, setIngestJob] = useState<HistoricalIngestJob | null>(null);
  const [ingestStarting, setIngestStarting] = useState(false);
  const [mapperUpdating, setMapperUpdating] = useState(false);

  const wsRefs = useRef<Record<string, WebSocket>>({});
  const logCursor = useRef<Record<string, number>>({});
  const ingestChunkCursor = useRef<Record<string, number>>({});

  const appendTerminal = (line: string) => {
    setExecutionLog((prev) => [...prev.slice(-1000), line]);
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
    () => mongoOptions.find((option) => option.id === selectedMongoOptionId) ?? null,
    [mongoOptions, selectedMongoOptionId],
  );

  const timeframeOptions = useMemo(() => {
    const values = new Set((selectedCatalog?.timeframes_available || []).map((tf) => tf.timeframe));
    if (!values.size) values.add('1day');
    return Array.from(values);
  }, [selectedCatalog]);

  const editorDirty = normalizeSource(strategySource) !== normalizeSource(savedSource);

  const ingestDisabledReason = useMemo(() => {
    if (ingestStarting) return 'Ingestion already in progress.';
    if (!selectedSearchInstrument) return 'Select one instrument from search results.';
    if (!canIngestInstrument(selectedSearchInstrument)) return `Unsupported instrument type: ${selectedSearchInstrument.instrument_type || 'unknown'}.`;
    if (!ingestFrom || !ingestTo) return 'Choose both from and to dates.';
    if (ingestFrom > ingestTo) return 'From date cannot be after To date.';
    return null;
  }, [ingestStarting, selectedSearchInstrument, ingestFrom, ingestTo]);

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
    const nextCatalog = fresh.catalog as CatalogEntry[];
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
        const nextResults = r.results as BacktestResult[];
        const nextCatalog = c.catalog as CatalogEntry[];
        const nextStrategies = s.strategies as Strategy[];

        setResults(nextResults);
        setCatalog(nextCatalog);
        setStrategies(nextStrategies);

        const firstStrategy = nextStrategies[0] ?? null;
        if (firstStrategy) {
          setSelectedStrategyId(firstStrategy.relative_path || firstStrategy.name);
          setStrategyName(stemFromStrategy(firstStrategy));
        }
        const firstCatalog = nextCatalog[0] ?? null;
        if (firstCatalog) {
          setInstrumentToken(String(firstCatalog.instrument_token));
          const firstTf = firstCatalog.timeframes_available?.[0];
          if (firstTf) {
            setTimeframe(firstTf.timeframe);
            setDateFrom(firstTf.date_from);
            setDateTo(firstTf.date_to);
            setSelectedMongoOptionId(`${firstCatalog.instrument_token}|${firstTf.timeframe}|${firstTf.date_from}|${firstTf.date_to}`);
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
      setSelectedSearchInstrument(null);
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
        const items = (data.items || []) as InstrumentSearchResult[];
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
    if (!ingestJob?.job_id) return undefined;
    if (ingestJob.status !== 'PENDING' && ingestJob.status !== 'RUNNING') return undefined;
    let active = true;
    const timer = window.setInterval(async () => {
      try {
        const doc = await getHistoricalIngestJob(ingestJob.job_id);
        if (!active) return;
        const job = doc as unknown as HistoricalIngestJob;
        const chunkSeen = ingestChunkCursor.current[job.job_id] ?? 0;
        const chunkNow = Number(job.current_chunk ?? 0);
        const totalChunks = Number(job.total_chunks ?? 0);
        if (chunkNow > chunkSeen && totalChunks > 0) {
          ingestChunkCursor.current[job.job_id] = chunkNow;
          appendTerminal(
            `[${formatIst(new Date().toISOString())}] [INFO] Ingest ${job.job_id}: chunk ${chunkNow}/${totalChunks}, rows=${job.rows ?? 0}.`,
          );
        }
        setIngestJob(job);
        if (job.status === 'COMPLETED' || job.status === 'NO_DATA' || job.status === 'FAILED') {
          if (job.status === 'COMPLETED') {
            appendTerminal(`[${formatIst(new Date().toISOString())}] [SUCCESS] Historical ingest completed (${job.inserted ?? 0} rows).`);
            const nextCatalog = await reloadCatalog();
            const request = job.request;
            if (request) {
              const tf = INTERVAL_TO_TIMEFRAME[request.interval] || request.interval;
              const matched = nextCatalog.find((c) => c.instrument_token === request.instrument_token);
              const matchedTf = matched?.timeframes_available?.find((x) => x.timeframe === tf)
                ?? matched?.timeframes_available?.[0];
              if (matched && matchedTf) selectCatalogEntry(matched, matchedTf);
            }
          } else if (job.status === 'NO_DATA') {
            appendTerminal(`[${formatIst(new Date().toISOString())}] [WARN] Historical ingest returned no candles.`);
          } else {
            appendTerminal(`[${formatIst(new Date().toISOString())}] [ERROR] Historical ingest failed: ${job.error_message || 'Unknown error'}`);
          }
        }
      } catch {
        if (!active) return;
      }
    }, 2000);

    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [ingestJob?.job_id, ingestJob?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!runningTaskIds.length) return undefined;
    // Slow fallback polling (WebSocket is primary).
    const timer = window.setInterval(async () => {
      try {
        const refreshed = await getBacktests();
        const next = refreshed.results as BacktestResult[];
        setResults(next);
        const active = new Set(
          next.filter((r) => r.status === 'RUNNING' || r.status === 'PENDING').map((r) => r.task_id),
        );
        setRunningTaskIds((prev) => prev.filter((id) => active.has(id)));
      } catch {
        // Keep running with existing WS streams.
      }
    }, 12000);
    return () => window.clearInterval(timer);
  }, [runningTaskIds, setResults]);

  const saveCurrentStrategy = async () => {
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
      const next = refreshed.strategies as Strategy[];
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
      const next = refreshed.strategies as Strategy[];
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
    const source = tfMeta?.data_source || entrySource(selectedCatalog);
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
      setResults(refreshed.results as BacktestResult[]);
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
      setResults(refreshed.results as BacktestResult[]);
    } catch (e: unknown) {
      setPageError(e instanceof Error ? e.message : 'Queue submission failed');
    } finally {
      setQueueSubmitting(false);
    }
  };

  const startIngest = async () => {
    setPageError(null);
    if (ingestDisabledReason) {
      setPageError(ingestDisabledReason);
      return;
    }
    if (!selectedSearchInstrument) return;

    setIngestStarting(true);
    try {
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
        request: {
          instrument_token: selectedSearchInstrument.instrument_token,
          tradingsymbol: selectedSearchInstrument.tradingsymbol,
          from_date: ingestFrom,
          to_date: ingestTo,
          interval: ingestInterval,
        },
      });
      ingestChunkCursor.current[resp.job_id] = 0;
      appendTerminal(`[${formatIst(new Date().toISOString())}] [INFO] Started historical ingest job ${resp.job_id}.`);
    } catch (e: unknown) {
      setPageError(e instanceof Error ? e.message : 'Failed to start historical ingest');
    } finally {
      setIngestStarting(false);
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
        setSearchResults((data.items || []) as InstrumentSearchResult[]);
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

  return (
    <div className="animate-in">
      <div className="page-header">
        <h1 className="page-title">Backtests</h1>
        <p className="page-subtitle">Legacy workspace flow on FastAPI + Mongo + WebSocket</p>
        <PageMetaBar
          items={['Editor Left', 'Control Rail Right', 'Terminal Bottom']}
          rightText="WebSocket-first execution stream"
        />
      </div>

      {pageError ? (
        <div className="card" style={{ marginBottom: 'var(--space-lg)', borderColor: 'var(--red-dim)', color: 'var(--red)' }}>
          {pageError}
        </div>
      ) : null}

      <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 2.1fr) minmax(320px, 1fr)', marginBottom: 'var(--space-lg)' }}>
        <div className="card" style={{ height: WORKSPACE_PANEL_HEIGHT, display: 'flex', flexDirection: 'column' }}>
          <div className="card-header">
            <span className="card-title">Strategy Workspace</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input
                className="input"
                style={{ width: 190 }}
                placeholder="new_strategy_name"
                value={newStrategyName}
                onChange={(e) => setNewStrategyName(e.target.value)}
              />
              <button className="btn btn-topnav btn-sm" disabled={!normalizeStrategyNameInput(newStrategyName)} onClick={createNewStrategy}>
                Create Strategy
              </button>
              <span className={`badge ${editorDirty ? 'badge-warning' : 'badge-success'}`}>{editorDirty ? 'Dirty' : 'Saved'}</span>
              <button className="btn btn-topnav btn-sm" disabled={!editorDirty || editorSaving} onClick={() => setStrategySource(savedSource)}>Revert</button>
              <button className="btn btn-topnav btn-sm" disabled={!editorDirty || editorSaving} onClick={saveCurrentStrategy}>
                {editorSaving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>

          <div className="grid grid-2" style={{ gap: 'var(--space-sm)', marginBottom: 'var(--space-sm)' }}>
            <div>
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
                      {s.name} ({id})
                    </option>
                  );
                })}
              </select>
            </div>
            <div>
              <label className="stat-label">Strategy Class</label>
              <select value={strategyClassName} onChange={(e) => setStrategyClassName(e.target.value)}>
                <option value="">Select class...</option>
                {strategyClasses.map((cls) => (
                  <option key={cls} value={cls}>{cls}</option>
                ))}
              </select>
            </div>
          </div>

          <div style={{ marginBottom: 'var(--space-sm)' }}>
            <label className="stat-label">Save Name</label>
            <input className="input" value={strategyName} onChange={(e) => setStrategyName(e.target.value)} />
          </div>

          <div style={{ flex: 1, minHeight: 0 }}>
            {editorLoading ? (
              <div style={{ color: 'var(--text-muted)' }}>Loading strategy source...</div>
            ) : (
              <CodeEditor value={strategySource} onChange={setStrategySource} height={560} />
            )}
          </div>

        </div>

        <div className="card" style={{ height: WORKSPACE_PANEL_HEIGHT, minWidth: CONTROL_RAIL_MIN_WIDTH, display: 'flex', flexDirection: 'column' }}>
          <div className="card-header"><span className="card-title">Control Rail</span></div>
          <div style={{ overflowY: 'auto', paddingRight: 6, minHeight: 0 }}>

          <details open>
            <summary style={{ cursor: 'pointer', fontWeight: 600, marginBottom: 8 }}>Data Selection</summary>
            <div style={{ display: 'grid', gap: 8, marginBottom: 12 }}>
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
                        className="btn btn-topnav btn-sm"
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
                        {option.tradingsymbol} | {option.instrument_token} | {option.timeframe} | {option.date_from} to {option.date_to} | bars {option.total_bars.toLocaleString()} | {option.source}
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
                  <div className="grid grid-2" style={{ gap: 8 }}>
                    <input className="input" type="date" value={dateFrom} min={selectedTfMeta?.date_from} max={selectedTfMeta?.date_to} onChange={(e) => setDateFrom(e.target.value)} />
                    <input className="input" type="date" value={dateTo} min={selectedTfMeta?.date_from} max={selectedTfMeta?.date_to} onChange={(e) => setDateTo(e.target.value)} />
                  </div>
                </>
              ) : (
                <>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                    Instrument search uses mapper files: <code>zerodha_instruments_latest.csv</code> + <code>zerodha_instruments_archive.csv</code>.
                  </div>
                  <label className="stat-label">Search Zerodha Instrument</label>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <input
                      className="input"
                      style={{ flex: 1 }}
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
                        className="btn btn-topnav btn-sm"
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
                  <div className="grid grid-2" style={{ gap: 8 }}>
                    <input className="input" type="date" value={ingestFrom} onChange={(e) => setIngestFrom(e.target.value)} />
                    <input className="input" type="date" value={ingestTo} onChange={(e) => setIngestTo(e.target.value)} />
                  </div>
                  <button className="btn btn-topnav btn-sm" disabled={Boolean(ingestDisabledReason)} onClick={startIngest}>
                    {ingestStarting ? 'Starting...' : 'Fetch to MongoDB'}
                  </button>
                  {ingestDisabledReason ? <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{ingestDisabledReason}</div> : null}
                  {ingestJob ? (
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                      Job {ingestJob.job_id}: <b>{ingestJob.status}</b>
                      {' | '}chunk={ingestJob.current_chunk ?? 0}/{ingestJob.total_chunks ?? 0}
                      {' | '}rows={ingestJob.rows ?? 0}
                      {' | '}inserted={ingestJob.inserted ?? 0}
                      {ingestJob.error_message ? ` | ${ingestJob.error_message}` : ''}
                    </div>
                  ) : null}
                </>
              )}
            </div>
          </details>

          <details open>
            <summary style={{ cursor: 'pointer', fontWeight: 600, marginBottom: 8 }}>Strategy Selection</summary>
            <div style={{ display: 'grid', gap: 8, marginBottom: 12 }}>
              <label className="stat-label">Selected Strategy ID</label>
              <input className="input" value={selectedStrategyId || '-'} readOnly />
              <label className="stat-label">Rename / Save Name</label>
              <input className="input" value={strategyName} onChange={(e) => setStrategyName(e.target.value)} />
              <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                Saving uses safe rename rules and path-stable <code>strategy_id</code> resolution.
              </div>
            </div>
          </details>

          <details open>
            <summary style={{ cursor: 'pointer', fontWeight: 600, marginBottom: 8 }}>Versioning</summary>
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <input type="checkbox" checked={versioningEnabled} onChange={(e) => setVersioningEnabled(e.target.checked)} />
              Save as versioned file (backend-driven)
            </label>
          </details>

          <details open>
            <summary style={{ cursor: 'pointer', fontWeight: 600, marginBottom: 8 }}>AI Powered Strategy Refiner</summary>
            <div style={{ color: 'var(--text-muted)', fontSize: '0.82rem', marginBottom: 12 }}>
              Placeholder section kept for old workspace parity. Hook your refiner endpoint here.
            </div>
          </details>

          <details open>
            <summary style={{ cursor: 'pointer', fontWeight: 600, marginBottom: 8 }}>Execution Config</summary>
            <div style={{ display: 'grid', gap: 8, marginBottom: 12 }}>
              <label className="stat-label">Initial Cash</label>
              <input className="input" type="number" min={1} value={capital} onChange={(e) => setCapital(e.target.value)} />
              <label className="stat-label">Commission</label>
              <input className="input" type="number" step="0.0001" min={0} value={commission} onChange={(e) => setCommission(e.target.value)} />
              <label className="stat-label">Slippage</label>
              <input className="input" type="number" step="0.0001" min={0} value={slippage} onChange={(e) => setSlippage(e.target.value)} />
              <div className="grid grid-2" style={{ gap: 8 }}>
                <div>
                  <label className="stat-label">Lot Size</label>
                  <input className="input" type="number" min={1} value={lotSize} onChange={(e) => setLotSize(e.target.value)} />
                </div>
                <div>
                  <label className="stat-label">Position Size</label>
                  <input className="input" type="number" min={1} value={positionSize} onChange={(e) => setPositionSize(e.target.value)} />
                </div>
              </div>
              <div className="grid grid-2" style={{ gap: 8 }}>
                <div>
                  <label className="stat-label">Max Positions</label>
                  <input className="input" type="number" min={1} value={maxPositions} onChange={(e) => setMaxPositions(e.target.value)} />
                </div>
                <div>
                  <label className="stat-label">Execution Mode</label>
                  <select value={executionMode} onChange={(e) => setExecutionMode(e.target.value)}>
                    <option value="market">market</option>
                    <option value="close">close</option>
                  </select>
                </div>
              </div>
              <div className="grid grid-2" style={{ gap: 8 }}>
                <div>
                  <label className="stat-label">Max Retries</label>
                  <input className="input" type="number" min={0} value={maxRetries} onChange={(e) => setMaxRetries(e.target.value)} />
                </div>
                <div>
                  <label className="stat-label">Task Timeout (s)</label>
                  <input className="input" type="number" min={10} value={taskTimeoutSeconds} onChange={(e) => setTaskTimeoutSeconds(e.target.value)} />
                </div>
              </div>
              <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                <input type="checkbox" checked={enforceMarketHours} onChange={(e) => setEnforceMarketHours(e.target.checked)} />
                Enforce market hours
              </label>
            </div>
          </details>

          <details open>
            <summary style={{ cursor: 'pointer', fontWeight: 600, marginBottom: 8 }}>Execute Strategy</summary>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
              <button className="btn btn-topnav btn-sm" onClick={addSelectionToQueue}>Add to Queue</button>
              <button className="btn btn-topnav btn-sm" onClick={runNow} disabled={loading || !!runningTaskIds.length}>Run Now</button>
              <button className="btn btn-topnav btn-sm" onClick={handleRunQueue} disabled={queueSubmitting || !queueItems.length || !!runningTaskIds.length}>
                {queueSubmitting ? 'Running...' : `Run Queue (${queueItems.length})`}
              </button>
              <button className="btn btn-topnav btn-sm" onClick={() => setQueueItems([])} disabled={!queueItems.length || queueSubmitting}>
                Clear Queue
              </button>
            </div>
            <div className="table-wrapper" style={{ maxHeight: 140, overflow: 'auto' }}>
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

      <div className="card" style={{ marginBottom: 'var(--space-xl)' }}>
        <div className="card-header">
          <span className="card-title">Execution Terminal</span>
          <div style={{ display: 'flex', gap: 8 }}>
            <span className={`badge ${runningTaskIds.length ? 'badge-warning' : 'badge-success'}`}>
              {runningTaskIds.length ? `Running ${runningTaskIds.length}` : 'Idle'}
            </span>
            <button className="btn btn-ghost btn-sm" onClick={() => setExecutionLog([])}>Clear</button>
          </div>
        </div>
        <div style={{ maxHeight: 280, overflow: 'auto', fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
          {executionLog.length ? executionLog.slice().reverse().map((line, idx) => (
            <div key={`${line}-${idx}`} style={{ padding: '4px 0', borderBottom: '1px dashed var(--border-subtle)' }}>{line}</div>
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
