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
  searchInstruments,
  startHistoricalIngest,
} from '../services/api';
import { useBacktestStore } from '../stores/backtestStore';
import type {
  BacktestResult,
  CatalogEntry,
  HistoricalIngestJob,
  InstrumentSearchResult,
  Strategy,
} from '../types/backtest';

type DataSourceFilter = 'all' | 'historical' | 'live' | 'mixed';

interface QueueItem {
  id: string;
  instrument_token: number;
  tradingsymbol: string;
  timeframe: string;
  date_from: string;
  date_to: string;
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

function formatInr(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '-';
  return `INR ${value.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
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
  if (!t) return true;
  return ['EQ', 'INDEX', 'ETF'].includes(t);
}

export default function BacktestPage() {
  const { results, strategies, catalog, setResults, setStrategies, setCatalog, updateResult } = useBacktestStore();

  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);
  const [executionLog, setExecutionLog] = useState<string[]>([]);
  const [runningTaskIds, setRunningTaskIds] = useState<string[]>([]);
  const [selectedResultId, setSelectedResultId] = useState<string | null>(null);

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

  const [dataSourceFilter, setDataSourceFilter] = useState<DataSourceFilter>('all');
  const [catalogQuery, setCatalogQuery] = useState('');
  const [instrumentToken, setInstrumentToken] = useState('');
  const [timeframe, setTimeframe] = useState('1day');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [queueItems, setQueueItems] = useState<QueueItem[]>([]);

  const [capital, setCapital] = useState('100000');
  const [commission, setCommission] = useState('0.0003');
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

  const wsRefs = useRef<Record<string, WebSocket>>({});
  const logCursor = useRef<Record<string, number>>({});

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

  const selectedResult = useMemo(
    () => results.find((item) => item.task_id === selectedResultId) ?? null,
    [results, selectedResultId],
  );

  const filteredCatalog = useMemo(() => {
    const q = catalogQuery.trim().toUpperCase();
    return catalog.filter((entry) => {
      const tfSources = new Set(
        (entry.timeframes_available || [])
          .map((tf) => String(tf.data_source || '').toLowerCase())
          .filter(Boolean),
      );
      const sourceOk = dataSourceFilter === 'all'
        ? true
        : tfSources.has(dataSourceFilter)
          || (dataSourceFilter === 'mixed' && tfSources.size > 1);
      if (!sourceOk) return false;
      if (!q) return true;
      return (
        entry.tradingsymbol.toUpperCase().includes(q)
        || String(entry.instrument_token).includes(q)
      );
    });
  }, [catalog, catalogQuery, dataSourceFilter]);

  const timeframeOptions = useMemo(() => {
    const values = new Set((selectedCatalog?.timeframes_available || []).map((tf) => tf.timeframe));
    if (!values.size) values.add('1day');
    return Array.from(values);
  }, [selectedCatalog]);

  const editorDirty = strategySource !== savedSource;

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
        const fallbackName = strategy?.name || strategyName;
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
          const [src, classesResp] = await Promise.all([
            getStrategySource(strategyName),
            getStrategyClasses(strategyName),
          ]);
          if (!mounted) return;
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
  }, [selectedStrategyId, strategies, strategyName]);

  useEffect(() => {
    if (!selectedCatalog || !selectedTfMeta) return;
    if (!timeframeOptions.includes(timeframe)) setTimeframe(selectedTfMeta.timeframe);
    if (!dateFrom || dateFrom < selectedTfMeta.date_from || dateFrom > selectedTfMeta.date_to) setDateFrom(selectedTfMeta.date_from);
    if (!dateTo || dateTo < selectedTfMeta.date_from || dateTo > selectedTfMeta.date_to) setDateTo(selectedTfMeta.date_to);
  }, [selectedCatalog, selectedTfMeta, timeframeOptions, timeframe, dateFrom, dateTo]);

  useEffect(() => {
    if (symbolQuery.trim().length < 2) {
      setSearchResults([]);
      setSearchWarning(symbolQuery.trim().length ? 'Type at least 2 characters to search.' : null);
      return undefined;
    }
    let active = true;
    const timer = window.setTimeout(async () => {
      setSearchBusy(true);
      try {
        const data = await searchInstruments(symbolQuery.trim(), 25);
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
  }, [symbolQuery]);

  useEffect(() => {
    if (!ingestJob?.job_id) return undefined;
    if (ingestJob.status !== 'PENDING' && ingestJob.status !== 'RUNNING') return undefined;
    let active = true;
    const timer = window.setInterval(async () => {
      try {
        const doc = await getHistoricalIngestJob(ingestJob.job_id);
        if (!active) return;
        const job = doc as unknown as HistoricalIngestJob;
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
    if (!strategyName.trim()) return;
    setEditorSaving(true);
    setPageError(null);
    try {
      const resp = await saveStrategy(strategyName.trim(), strategySource, {
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
      appendTerminal(`[${formatIst(new Date().toISOString())}] [SUCCESS] Saved strategy ${strategyName.trim()}.`);
    } catch (e: unknown) {
      setPageError(e instanceof Error ? e.message : 'Failed to save strategy');
    } finally {
      setEditorSaving(false);
    }
  };

  const createNewStrategy = async () => {
    const name = newStrategyName.trim();
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
      max_retries: Number(maxRetries),
      task_timeout_seconds: Number(taskTimeoutSeconds),
      enforce_market_hours: enforceMarketHours,
    });
    const taskId = resp.task_id;
    setRunningTaskIds((prev) => [...prev, taskId]);
    setSelectedResultId(taskId);
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
      for (const item of queueItems) {
        const { id: _id, ...requestItem } = item;
        await submitRun(requestItem);
      }
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
    if (!selectedSearchInstrument) {
      setPageError('Select an instrument from search results first.');
      return;
    }
    if (!canIngestInstrument(selectedSearchInstrument)) {
      setPageError(`Unsupported instrument type for historical ingestion: ${selectedSearchInstrument.instrument_type || 'unknown'}.`);
      return;
    }
    if (!ingestFrom || !ingestTo || ingestFrom > ingestTo) {
      setPageError('Provide a valid historical ingestion date range.');
      return;
    }

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
      appendTerminal(`[${formatIst(new Date().toISOString())}] [INFO] Started historical ingest job ${resp.job_id}.`);
    } catch (e: unknown) {
      setPageError(e instanceof Error ? e.message : 'Failed to start historical ingest');
    } finally {
      setIngestStarting(false);
    }
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
        <div className="card">
          <div className="card-header">
            <span className="card-title">Strategy Workspace</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span className={`badge ${editorDirty ? 'badge-warning' : 'badge-success'}`}>{editorDirty ? 'Dirty' : 'Saved'}</span>
              <button className="btn btn-ghost btn-sm" disabled={!editorDirty || editorSaving} onClick={() => setStrategySource(savedSource)}>Revert</button>
              <button className="btn btn-primary btn-sm" disabled={!editorDirty || editorSaving} onClick={saveCurrentStrategy}>
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
                  const id = e.target.value;
                  setSelectedStrategyId(id);
                  const strategy = strategies.find((s) => (s.relative_path || s.name) === id) ?? null;
                  setStrategyName(stemFromStrategy(strategy));
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

          {editorLoading ? (
            <div style={{ color: 'var(--text-muted)' }}>Loading strategy source...</div>
          ) : (
            <CodeEditor value={strategySource} onChange={setStrategySource} height={640} />
          )}

          {selectedResult ? (
            <div className="card" style={{ marginTop: 'var(--space-md)', padding: 'var(--space-md)' }}>
              <div className="card-header"><span className="card-title">Selected Result</span></div>
              <div style={{ display: 'grid', gap: 6, fontSize: '0.84rem', color: 'var(--text-secondary)' }}>
                <div><b>Task:</b> <span style={{ fontFamily: 'var(--font-mono)' }}>{selectedResult.task_id}</span></div>
                <div><b>Status:</b> {selectedResult.status}</div>
                <div><b>Final Value:</b> {formatInr(selectedResult.final_value)}</div>
                <div><b>Started:</b> {formatIst(selectedResult.started_at)}</div>
                <div><b>Completed:</b> {formatIst(selectedResult.completed_at)}</div>
                {selectedResult.error_message ? <div style={{ color: 'var(--red)' }}><b>Error:</b> {selectedResult.error_message}</div> : null}
                <div>
                  <b>Metrics</b>
                  <pre style={{ marginTop: 6, background: '#f8fafc', border: '1px solid var(--border-subtle)', borderRadius: 8, padding: 8, overflow: 'auto', maxHeight: 120 }}>
                    {JSON.stringify(selectedResult.metrics || {}, null, 2)}
                  </pre>
                </div>
                <div>
                  <b>Trades</b>
                  <div className="table-wrapper" style={{ maxHeight: 150, overflow: 'auto', marginTop: 6 }}>
                    <table>
                      <thead><tr><th>Entry</th><th>Exit</th><th>Dir</th><th>PNL</th></tr></thead>
                      <tbody>
                        {(selectedResult.trades || []).map((trade, idx) => (
                          <tr key={`${selectedResult.task_id}-trade-${idx}`}>
                            <td>{trade.entry_date}</td>
                            <td>{trade.exit_date}</td>
                            <td>{trade.direction}</td>
                            <td style={{ color: trade.pnl >= 0 ? 'var(--green)' : 'var(--red)' }}>{trade.pnl.toFixed(2)}</td>
                          </tr>
                        ))}
                        {!selectedResult.trades?.length ? <tr><td colSpan={4} style={{ textAlign: 'center' }}>No trades</td></tr> : null}
                      </tbody>
                    </table>
                  </div>
                </div>
                <div>
                  <b>Result Logs</b>
                  <div style={{ maxHeight: 130, overflow: 'auto', marginTop: 6, fontFamily: 'var(--font-mono)', fontSize: '0.76rem' }}>
                    {(selectedResult.log_lines || []).length
                      ? (selectedResult.log_lines || []).map((line, idx) => <div key={`${selectedResult.task_id}-log-${idx}`}>{line}</div>)
                      : <span style={{ color: 'var(--text-muted)' }}>No logs</span>}
                  </div>
                </div>
              </div>
            </div>
          ) : null}
        </div>

        <div className="card">
          <div className="card-header"><span className="card-title">Control Rail</span></div>

          <details open>
            <summary style={{ cursor: 'pointer', fontWeight: 600, marginBottom: 8 }}>Data Selection</summary>
            <div style={{ display: 'grid', gap: 8, marginBottom: 12 }}>
              <select value={dataSourceFilter} onChange={(e) => setDataSourceFilter(e.target.value as DataSourceFilter)}>
                <option value="all">All Sources</option>
                <option value="historical">Historical</option>
                <option value="live">Live</option>
                <option value="mixed">Mixed</option>
              </select>
              <input className="input" placeholder="Search symbol/token" value={catalogQuery} onChange={(e) => setCatalogQuery(e.target.value)} />

              {!catalog.length ? (
                <div style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>
                  Catalog is empty. Fetch historical data from Zerodha below to populate MongoDB first.
                </div>
              ) : null}

              <div className="table-wrapper" style={{ maxHeight: 180, overflow: 'auto' }}>
                <table>
                  <thead><tr><th>Symbol</th><th>Token</th><th>TF</th><th>Range</th><th>Bars</th><th>Source</th></tr></thead>
                  <tbody>
                    {filteredCatalog.flatMap((entry) =>
                      (entry.timeframes_available || []).map((tf) => (
                        <tr
                          key={`${entry.instrument_token}-${tf.timeframe}-${tf.date_from}-${tf.date_to}`}
                          style={{ cursor: 'pointer', background: String(entry.instrument_token) === instrumentToken && tf.timeframe === timeframe ? 'rgba(37,99,235,0.08)' : undefined }}
                          onClick={() => selectCatalogEntry(entry, tf)}
                        >
                          <td>{entry.tradingsymbol}</td>
                          <td style={{ fontFamily: 'var(--font-mono)' }}>{entry.instrument_token}</td>
                          <td>{tf.timeframe}</td>
                          <td style={{ fontSize: '0.75rem' }}>{tf.date_from} to {tf.date_to}</td>
                          <td style={{ fontFamily: 'var(--font-mono)' }}>{tf.total_bars.toLocaleString()}</td>
                          <td>{tf.data_source || entrySource(entry)}</td>
                        </tr>
                      )),
                    )}
                    {!filteredCatalog.length ? <tr><td colSpan={6} style={{ textAlign: 'center' }}>No rows</td></tr> : null}
                  </tbody>
                </table>
              </div>
              <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
                {timeframeOptions.map((tf) => <option key={tf} value={tf}>{tf}</option>)}
              </select>
              <div className="grid grid-2" style={{ gap: 8 }}>
                <input className="input" type="date" value={dateFrom} min={selectedTfMeta?.date_from} max={selectedTfMeta?.date_to} onChange={(e) => setDateFrom(e.target.value)} />
                <input className="input" type="date" value={dateTo} min={selectedTfMeta?.date_from} max={selectedTfMeta?.date_to} onChange={(e) => setDateTo(e.target.value)} />
              </div>
            </div>
          </details>

          <details open>
            <summary style={{ cursor: 'pointer', fontWeight: 600, marginBottom: 8 }}>Fetch Historical Data from Zerodha</summary>
            <div style={{ display: 'grid', gap: 8, marginBottom: 12 }}>
              <input
                className="input"
                placeholder="Search symbol (e.g. RELIANCE)"
                value={symbolQuery}
                onChange={(e) => setSymbolQuery(e.target.value)}
              />
              {searchBusy ? <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>Searching instruments...</div> : null}
              {searchWarning ? <div style={{ color: 'var(--amber)', fontSize: '0.8rem' }}>{searchWarning}</div> : null}

              <div className="table-wrapper" style={{ maxHeight: 150, overflow: 'auto' }}>
                <table>
                  <thead><tr><th>Symbol</th><th>Token</th><th>Type</th></tr></thead>
                  <tbody>
                    {searchResults.map((item) => (
                      <tr
                        key={`${item.instrument_token}-${item.tradingsymbol}`}
                        style={{ cursor: 'pointer', background: selectedSearchInstrument?.instrument_token === item.instrument_token ? 'rgba(37,99,235,0.08)' : undefined }}
                        onClick={() => setSelectedSearchInstrument(item)}
                      >
                        <td>{item.tradingsymbol}</td>
                        <td style={{ fontFamily: 'var(--font-mono)' }}>{item.instrument_token}</td>
                        <td>{item.instrument_type || '-'}</td>
                      </tr>
                    ))}
                    {!searchResults.length ? <tr><td colSpan={3} style={{ textAlign: 'center' }}>No matches</td></tr> : null}
                  </tbody>
                </table>
              </div>

              <select value={ingestInterval} onChange={(e) => setIngestInterval(e.target.value)}>
                {INGEST_INTERVALS.map((it) => <option key={it} value={it}>{it}</option>)}
              </select>
              <div className="grid grid-2" style={{ gap: 8 }}>
                <input className="input" type="date" value={ingestFrom} onChange={(e) => setIngestFrom(e.target.value)} />
                <input className="input" type="date" value={ingestTo} onChange={(e) => setIngestTo(e.target.value)} />
              </div>
              <button className="btn btn-primary btn-sm" disabled={ingestStarting} onClick={startIngest}>
                {ingestStarting ? 'Starting...' : 'Fetch to MongoDB'}
              </button>
              {ingestJob ? (
                <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  Job {ingestJob.job_id}: <b>{ingestJob.status}</b>
                  {' | '}rows={ingestJob.rows ?? 0}
                  {' | '}inserted={ingestJob.inserted ?? 0}
                  {ingestJob.error_message ? ` | ${ingestJob.error_message}` : ''}
                </div>
              ) : null}
            </div>
          </details>

          <details open>
            <summary style={{ cursor: 'pointer', fontWeight: 600, marginBottom: 8 }}>Strategy Selection</summary>
            <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: 12 }}>
              Strategy identity is path-stable via <code>strategy_id</code>, with class-level selection.
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
              <input className="input" type="number" value={capital} onChange={(e) => setCapital(e.target.value)} placeholder="Initial Capital" />
              <input className="input" type="number" step="0.0001" value={commission} onChange={(e) => setCommission(e.target.value)} placeholder="Commission" />
              <div className="grid grid-2" style={{ gap: 8 }}>
                <input className="input" type="number" min={0} value={maxRetries} onChange={(e) => setMaxRetries(e.target.value)} placeholder="Max Retries" />
                <input className="input" type="number" min={10} value={taskTimeoutSeconds} onChange={(e) => setTaskTimeoutSeconds(e.target.value)} placeholder="Timeout (s)" />
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
              <button className="btn btn-ghost btn-sm" onClick={addSelectionToQueue}>Add to Queue</button>
              <button className="btn btn-primary btn-sm" onClick={runNow} disabled={loading || !!runningTaskIds.length}>Run Now</button>
              <button className="btn btn-primary btn-sm" onClick={handleRunQueue} disabled={queueSubmitting || !queueItems.length || !!runningTaskIds.length}>
                {queueSubmitting ? 'Running...' : `Run Queue (${queueItems.length})`}
              </button>
            </div>
            <div className="table-wrapper" style={{ maxHeight: 140, overflow: 'auto' }}>
              <table>
                <thead><tr><th>Symbol</th><th>TF</th><th>Range</th></tr></thead>
                <tbody>
                  {queueItems.map((item) => (
                    <tr key={item.id}>
                      <td>{item.tradingsymbol}</td>
                      <td>{item.timeframe}</td>
                      <td style={{ fontSize: '0.76rem' }}>{item.date_from} to {item.date_to}</td>
                    </tr>
                  ))}
                  {!queueItems.length ? <tr><td colSpan={3} style={{ textAlign: 'center' }}>Queue empty</td></tr> : null}
                </tbody>
              </table>
            </div>
          </details>

          <details open>
            <summary style={{ cursor: 'pointer', fontWeight: 600, marginBottom: 8 }}>Create New Strategy</summary>
            <div style={{ display: 'grid', gap: 8, marginBottom: 12 }}>
              <input className="input" placeholder="Strategy name" value={newStrategyName} onChange={(e) => setNewStrategyName(e.target.value)} />
              <button className="btn btn-ghost btn-sm" disabled={!newStrategyName.trim()} onClick={createNewStrategy}>Create</button>
            </div>
          </details>

          <details open>
            <summary style={{ cursor: 'pointer', fontWeight: 600, marginBottom: 8 }}>Strategy Result Loader</summary>
            <div className="table-wrapper" style={{ maxHeight: 220, overflow: 'auto' }}>
              <table>
                <thead><tr><th>Status</th><th>Strategy</th><th>Value</th></tr></thead>
                <tbody>
                  {results.map((r) => (
                    <tr
                      key={r.task_id}
                      style={{ cursor: 'pointer', background: selectedResultId === r.task_id ? 'rgba(37,99,235,0.08)' : undefined }}
                      onClick={() => setSelectedResultId(r.task_id)}
                    >
                      <td>{r.status}</td>
                      <td>{r.strategy_name}</td>
                      <td style={{ fontFamily: 'var(--font-mono)' }}>{formatInr(r.final_value)}</td>
                    </tr>
                  ))}
                  {!results.length ? <tr><td colSpan={3} style={{ textAlign: 'center' }}>No results</td></tr> : null}
                </tbody>
              </table>
            </div>
          </details>
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
