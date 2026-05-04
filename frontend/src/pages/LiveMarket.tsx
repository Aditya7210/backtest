import { useEffect, useMemo, useState } from 'react';
import LightweightCandlestickChart from '../components/LightweightCandlestickChart';
import LightweightLineChart, { type LinePoint } from '../components/LightweightLineChart';
import SearchableDropdown, { type SearchableOption } from '../components/SearchableDropdown';
import Tooltip from '../components/Tooltip';
import {
  computeIndicators,
  getCollectorStatus,
  getIndicators,
  getLatestMarketTick,
  getLiveInstruments,
  getMarketView,
  getMarketBars,
  getSnapshot,
} from '../services/api';
import type { IndicatorMetadata, IndicatorSelection, IndicatorSeries } from '../types/indicators';
import type { LiveInstrumentItem, LiveTick, LiveTimeframe, OHLCVBar } from '../types/market';
import { applyLiveTickToBars } from '../features/live-market/liveTickCandle';
import {
  basisFromSpotAndFuture,
  buildInventoryOptions,
  parseMarketViewPayload,
  type MarketViewPayload,
} from '../features/live-market/marketView';
import { LIVE_TIMEFRAMES } from '../features/live-market/timeframes';
import { formatIsoIst, todayIstDate } from '../features/time/ist';

type UnderlyingMode = 'AUTO' | 'NIFTY' | 'BANKNIFTY';

interface OptionChainRow {
  strike: number;
  expiry?: string;
  ce_ltp: number;
  pe_ltp: number;
  ce_oi: number;
  pe_oi: number;
  strike_pcr: number | null;
}

interface InventoryFilters {
  q: string;
  instrumentType: string;
  underlying: string;
  expiry: string;
  timeframe: string;
  tradingDate: string;
  activeOnly: boolean;
}

function asObj(v: unknown): Record<string, unknown> {
  return v && typeof v === 'object' ? (v as Record<string, unknown>) : {};
}

function asNum(v: unknown): number | null {
  if (typeof v === 'number' && Number.isFinite(v)) return v;
  if (typeof v === 'string') {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function asText(v: unknown): string {
  return typeof v === 'string' ? v : '';
}

function toUnixSeconds(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return Math.floor(value);
  if (typeof value !== 'string' || !value) return null;
  const safe = /[zZ]$/.test(value) || /[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`;
  const millis = Date.parse(safe);
  return Number.isFinite(millis) ? Math.floor(millis / 1000) : null;
}

function parseBars(value: unknown): OHLCVBar[] {
  if (!Array.isArray(value)) return [];
  const parsed: OHLCVBar[] = [];
  for (const row of value) {
    const record = asObj(row);
    const time = asNum(record.time) ?? toUnixSeconds(record.timestamp);
    const open = asNum(record.open);
    const high = asNum(record.high);
    const low = asNum(record.low);
    const close = asNum(record.close);
    const volume = asNum(record.volume) ?? 0;
    if (time == null || open == null || high == null || low == null || close == null) continue;
    const oi = asNum(record.oi);
    parsed.push({ time, open, high, low, close, volume, oi });
  }
  parsed.sort((a, b) => a.time - b.time);
  return parsed;
}

function parseLiveTick(value: unknown): LiveTick | null {
  const row = asObj(value);
  const token = asNum(row.instrument_token);
  const price = asNum(row.last_price);
  const time = asNum(row.time) ?? toUnixSeconds(row.timestamp);
  if (token == null || price == null || time == null) return null;
  return {
    instrument_token: token,
    last_price: price,
    volume_traded: asNum(row.volume_traded) ?? undefined,
    oi: asNum(row.oi) ?? undefined,
    time,
    timestamp: asText(row.timestamp) || undefined,
  };
}

function parseInventoryItems(raw: unknown): LiveInstrumentItem[] {
  if (!Array.isArray(raw)) return [];
  const out: LiveInstrumentItem[] = [];
  for (const row of raw) {
    const r = asObj(row);
    const token = asNum(r.instrument_token);
    const symbol = asText(r.tradingsymbol) || (token != null ? String(token) : '');
    if (token == null || !symbol) continue;
    out.push({
      instrument_token: token,
      tradingsymbol: symbol,
      instrument_type: asText(r.instrument_type) || 'unknown',
      data_source: asText(r.data_source) || 'historical',
      timeframe: asText(r.timeframe) || '1min',
      trading_date: asText(r.trading_date),
      first_bar_at: asText(r.first_bar_at) || null,
      last_bar_at: asText(r.last_bar_at) || null,
      first_bar_time: asNum(r.first_bar_time),
      last_bar_time: asNum(r.last_bar_time),
      total_bars: asNum(r.total_bars) ?? 0,
      last_close: asNum(r.last_close),
      exchange: asText(r.exchange),
      segment: asText(r.segment),
      underlying: asText(r.underlying),
      expiry: asText(r.expiry),
      strike: asNum(r.strike),
      option_type: asText(r.option_type),
      is_active: Boolean(r.is_active),
      stale_seconds: asNum(r.stale_seconds),
    });
  }
  return out;
}

function parseIndicatorMeta(raw: unknown): IndicatorMetadata[] {
  if (!Array.isArray(raw)) return [];
  const out: IndicatorMetadata[] = [];
  for (const row of raw) {
    const rec = asObj(row);
    const name = asText(rec.name);
    if (!name) continue;
    out.push({
      name,
      label: asText(rec.label) || name.toUpperCase(),
      category: asText(rec.category) || 'General',
      pane: asText(rec.pane) || 'price',
      params: Array.isArray(rec.params) ? (rec.params as IndicatorMetadata['params']) : [],
      presets: Array.isArray(rec.presets) ? (rec.presets as IndicatorMetadata['presets']) : [],
    });
  }
  return out;
}

function parseIndicatorSeries(raw: unknown): IndicatorSeries[] {
  if (!Array.isArray(raw)) return [];
  const out: IndicatorSeries[] = [];
  for (const row of raw) {
    const rec = asObj(row);
    const id = asText(rec.id);
    const name = asText(rec.name);
    if (!id || !name) continue;
    const pointsRaw = Array.isArray(rec.points) ? rec.points : [];
    const points = pointsRaw
      .map((p) => {
        const pr = asObj(p);
        const time = asNum(pr.time);
        const value = asNum(pr.value);
        if (time == null || value == null) return null;
        return { time, value };
      })
      .filter((x): x is { time: number; value: number } => x !== null);
    if (!points.length) continue;
    out.push({
      id,
      name,
      label: asText(rec.label) || name,
      pane: asText(rec.pane) || 'price',
      params: asObj(rec.params) as Record<string, number | string | boolean>,
      color: asText(rec.color) || '#4F46E5',
      points,
    });
  }
  return out;
}

function getSnapshotData(payload: unknown): { data: Record<string, unknown>; generatedAt: number | null } {
  const root = asObj(payload);
  const nested = asObj(root.data);
  const data = Object.keys(nested).length ? nested : root;
  const generatedAt = toUnixSeconds(root.generated_at) ?? toUnixSeconds(data.generated_at);
  return { data, generatedAt };
}

function parseOptionRows(atmData: Record<string, unknown>, pcrData: Record<string, unknown>, underlying: 'NIFTY' | 'BANKNIFTY'): OptionChainRow[] {
  const chainRoot = { ...asObj(pcrData.option_chain), ...asObj(atmData.option_chain) };
  const rowsRaw = Array.isArray(chainRoot[underlying]) ? chainRoot[underlying] : [];
  const rows: OptionChainRow[] = [];
  for (const row of rowsRaw) {
    const rec = asObj(row);
    const strike = asNum(rec.strike);
    const ceLtp = asNum(rec.ce_ltp);
    const peLtp = asNum(rec.pe_ltp);
    const ceOi = asNum(rec.ce_oi);
    const peOi = asNum(rec.pe_oi);
    const strikePcr = asNum(rec.strike_pcr);
    if (strike == null || ceLtp == null || peLtp == null || ceOi == null || peOi == null) continue;
    rows.push({
      strike,
      expiry: asText(rec.expiry) || undefined,
      ce_ltp: ceLtp,
      pe_ltp: peLtp,
      ce_oi: ceOi,
      pe_oi: peOi,
      strike_pcr: strikePcr,
    });
  }
  return rows.sort((a, b) => a.strike - b.strike);
}

function nearestStrike(strikes: number[], reference: number): number | null {
  if (!strikes.length) return null;
  let best = strikes[0];
  let distance = Math.abs(best - reference);
  for (let i = 1; i < strikes.length; i += 1) {
    const d = Math.abs(strikes[i] - reference);
    if (d < distance) {
      best = strikes[i];
      distance = d;
    }
  }
  return best;
}

function defaultParamsFor(meta: IndicatorMetadata): Record<string, number | string | boolean> {
  const out: Record<string, number | string | boolean> = {};
  for (const p of meta.params || []) {
    if (p.default != null) out[p.name] = p.default as number | string | boolean;
  }
  return out;
}

function inferUnderlying(symbol: string): 'NIFTY' | 'BANKNIFTY' {
  const up = symbol.toUpperCase();
  if (up.includes('BANK')) return 'BANKNIFTY';
  return 'NIFTY';
}

export default function LiveMarket() {
  const [inventory, setInventory] = useState<LiveInstrumentItem[]>([]);
  const [inventoryFilterMeta, setInventoryFilterMeta] = useState<Record<string, unknown>>({});
  const [selectedInstrumentKey, setSelectedInstrumentKey] = useState('');
  const [filters, setFilters] = useState<InventoryFilters>({
    q: '',
    instrumentType: 'all',
    underlying: 'all',
    expiry: 'all',
    timeframe: '1min',
    tradingDate: todayIstDate(),
    activeOnly: true,
  });
  const [barsByTimeframe, setBarsByTimeframe] = useState<Record<string, OHLCVBar[]>>({});
  const [primaryTimeframe, setPrimaryTimeframe] = useState<LiveTimeframe>('1min');
  const [overlayTimeframes, setOverlayTimeframes] = useState<LiveTimeframe[]>([]);
  const [liveTick, setLiveTick] = useState<LiveTick | null>(null);
  const [tickUpdatesEnabled, setTickUpdatesEnabled] = useState(true);
  const [autoScrollEnabled, setAutoScrollEnabled] = useState(true);
  const [loadingBars, setLoadingBars] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<string | null>(null);
  const [crosshairTime, setCrosshairTime] = useState<number | null>(null);
  const [collectorStatus, setCollectorStatus] = useState<Record<string, unknown>>({});

  const [marketView, setMarketView] = useState<MarketViewPayload>({
    generated_at: null,
    market_view: { NIFTY: { spot: null, futures: [] }, BANKNIFTY: { spot: null, futures: [] } },
  });
  const [pcrData, setPcrData] = useState<Record<string, unknown>>({});
  const [vixData, setVixData] = useState<Record<string, unknown>>({});
  const [atmData, setAtmData] = useState<Record<string, unknown>>({});
  const [underlyingMode, setUnderlyingMode] = useState<UnderlyingMode>('AUTO');
  const [selectedChainExpiry, setSelectedChainExpiry] = useState<string>('ALL');
  const [showOptionsInDropdown, setShowOptionsInDropdown] = useState(false);

  const [indicatorMeta, setIndicatorMeta] = useState<IndicatorMetadata[]>([]);
  const [selectedIndicators, setSelectedIndicators] = useState<IndicatorSelection[]>([]);
  const [indicatorToAdd, setIndicatorToAdd] = useState('');
  const [indicatorSeries, setIndicatorSeries] = useState<IndicatorSeries[]>([]);
  const [indicatorWarnings, setIndicatorWarnings] = useState<string[]>([]);
  const [indicatorLoading, setIndicatorLoading] = useState(false);

  const selectedInstrument = useMemo(
    () => inventory.find((x) => `${x.instrument_token}|${x.timeframe}|${x.trading_date}` === selectedInstrumentKey) ?? null,
    [inventory, selectedInstrumentKey],
  );
  const primaryBars = useMemo(
    () => barsByTimeframe[primaryTimeframe] ?? [],
    [barsByTimeframe, primaryTimeframe],
  );
  const bars = useMemo(
    () => (tickUpdatesEnabled ? applyLiveTickToBars(primaryBars, liveTick, primaryTimeframe) : primaryBars),
    [primaryBars, liveTick, primaryTimeframe, tickUpdatesEnabled],
  );

  const effectiveUnderlying = useMemo<'NIFTY' | 'BANKNIFTY'>(() => {
    if (underlyingMode === 'NIFTY') return 'NIFTY';
    if (underlyingMode === 'BANKNIFTY') return 'BANKNIFTY';
    return inferUnderlying(selectedInstrument?.tradingsymbol ?? 'NIFTY');
  }, [underlyingMode, selectedInstrument]);

  const optionRows = useMemo(
    () => parseOptionRows(atmData, pcrData, effectiveUnderlying),
    [atmData, pcrData, effectiveUnderlying],
  );
  const chainExpiries = useMemo(
    () => Array.from(new Set(optionRows.map((x) => x.expiry).filter((x): x is string => Boolean(x)))).sort(),
    [optionRows],
  );

  useEffect(() => {
    if (selectedChainExpiry !== 'ALL' && !chainExpiries.includes(selectedChainExpiry)) {
      setSelectedChainExpiry('ALL');
    }
  }, [chainExpiries, selectedChainExpiry]);
  useEffect(() => {
    setOverlayTimeframes((prev) => prev.filter((tf) => tf !== primaryTimeframe));
  }, [primaryTimeframe]);

  const filteredOptionRows = useMemo(
    () => (selectedChainExpiry === 'ALL' ? optionRows : optionRows.filter((x) => x.expiry === selectedChainExpiry)),
    [optionRows, selectedChainExpiry],
  );

  const spot = bars.length ? bars[bars.length - 1].close : null;
  const atmStrike = useMemo(() => {
    if (!spot) return null;
    return nearestStrike(filteredOptionRows.map((r) => r.strike), spot);
  }, [spot, filteredOptionRows]);

  const focusedStrike = useMemo(() => {
    if (!crosshairTime || !filteredOptionRows.length) return atmStrike;
    const bar = bars.find((b) => b.time === crosshairTime);
    if (!bar) return atmStrike;
    return nearestStrike(filteredOptionRows.map((r) => r.strike), bar.close);
  }, [crosshairTime, filteredOptionRows, bars, atmStrike]);

  const optionRowsVisible = useMemo(() => {
    if (!filteredOptionRows.length) return [];
    const center = focusedStrike ?? optionRows[Math.floor(optionRows.length / 2)].strike;
    return filteredOptionRows
      .slice()
      .sort((a, b) => Math.abs(a.strike - center) - Math.abs(b.strike - center))
      .slice(0, 24)
      .sort((a, b) => a.strike - b.strike);
  }, [filteredOptionRows, focusedStrike, optionRows]);

  const indicatorOptions = useMemo<SearchableOption[]>(
    () => indicatorMeta.map((x) => ({ id: x.name, label: `${x.label} (${x.name})`, searchText: `${x.name} ${x.label} ${x.category}` })),
    [indicatorMeta],
  );

  const inventoryOptions = useMemo<SearchableOption[]>(
    () => buildInventoryOptions(inventory, showOptionsInDropdown),
    [inventory, showOptionsInDropdown],
  );

  const overlaySeries = useMemo(
    () =>
      indicatorSeries
        .filter((x) => String(x.pane).toLowerCase() === 'price')
        .map((x) => ({ key: x.id, label: x.label, color: x.color || '#4F46E5', data: x.points })),
    [indicatorSeries],
  );
  const timeframeCandleOverlays = useMemo(
    () =>
      overlayTimeframes
        .map((tf) => ({
          key: `tf-${tf}`,
          label: `TF ${tf}`,
          bars: barsByTimeframe[tf] ?? [],
          upColor: 'rgba(79,70,229,0.25)',
          downColor: 'rgba(14,165,233,0.25)',
        }))
        .filter((item) => item.bars.length > 0),
    [barsByTimeframe, overlayTimeframes],
  );

  const oscillatorSeries = useMemo(
    () =>
      indicatorSeries
        .filter((x) => String(x.pane).toLowerCase() !== 'price')
        .map((x) => ({ id: x.id, label: x.label, color: x.color || '#7C3AED', data: x.points as LinePoint[] })),
    [indicatorSeries],
  );

  useEffect(() => {
    let active = true;
    const loadIndicatorMeta = async () => {
      try {
        const resp = await getIndicators();
        if (!active) return;
        setIndicatorMeta(parseIndicatorMeta((resp as { indicators?: unknown }).indicators));
      } catch (e: unknown) {
        if (!active) return;
        setError(e instanceof Error ? e.message : 'Failed to load indicators');
      }
    };
    loadIndicatorMeta();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    let timer: number | null = null;
    const fetchInventory = async () => {
      try {
        const resp = await getLiveInstruments({
          q: filters.q,
          instrument_type: filters.instrumentType,
          underlying: filters.underlying,
          expiry: filters.expiry,
          timeframe: filters.timeframe,
          trading_date: filters.tradingDate || undefined,
          active_only: filters.activeOnly,
          stale_threshold_seconds: 180,
          limit: 1200,
        });
        if (!active) return;
        const parsed = parseInventoryItems((resp as { items?: unknown }).items);
        setInventory(parsed);
        setInventoryFilterMeta(asObj((resp as { filters?: unknown }).filters));
        setSelectedInstrumentKey((prev) => {
          if (parsed.some((x) => `${x.instrument_token}|${x.timeframe}|${x.trading_date}` === prev)) return prev;
          if (!parsed.length) return '';
          const pick = parsed[0];
          return `${pick.instrument_token}|${pick.timeframe}|${pick.trading_date}`;
        });
        setLastUpdate(new Date().toISOString());
      } catch (e: unknown) {
        if (!active) return;
        setError(e instanceof Error ? e.message : 'Failed to load live inventory');
      }
    };
    fetchInventory();
    timer = window.setInterval(fetchInventory, 10000);
    return () => {
      active = false;
      if (timer != null) window.clearInterval(timer);
    };
  }, [filters]);

  useEffect(() => {
    if (!selectedInstrument) return;
    let active = true;
    let timer: number | null = null;
    const fetchBarsAndStatus = async () => {
      setLoadingBars(true);
      try {
        const requestedFrames = Array.from(new Set<LiveTimeframe>([primaryTimeframe, ...overlayTimeframes]));
        const [barsResponses, statusResp] = await Promise.all([
          Promise.all(
            requestedFrames.map((tf) =>
              getMarketBars(selectedInstrument.instrument_token, tf, selectedInstrument.trading_date),
            ),
          ),
          getCollectorStatus(),
        ]);
        if (!active) return;
        const nextBars: Record<string, OHLCVBar[]> = {};
        for (let i = 0; i < requestedFrames.length; i += 1) {
          const tf = requestedFrames[i];
          const barsResp = barsResponses[i] as { bars?: unknown };
          nextBars[tf] = parseBars(barsResp.bars);
        }
        setBarsByTimeframe(nextBars);
        setCollectorStatus(asObj(statusResp));
        setLastUpdate(new Date().toISOString());
        setError(null);
      } catch (e: unknown) {
        if (!active) return;
        setError(e instanceof Error ? e.message : 'Failed to fetch live bars');
      } finally {
        if (active) setLoadingBars(false);
      }
    };
    fetchBarsAndStatus();
    timer = window.setInterval(fetchBarsAndStatus, 5000);
    return () => {
      active = false;
      if (timer != null) window.clearInterval(timer);
    };
  }, [overlayTimeframes, primaryTimeframe, selectedInstrument]);

  useEffect(() => {
    let active = true;
    let timer: number | null = null;
    const fetchSnapshots = async () => {
      try {
        const [marketViewResp, pcrResp, vixResp, atmResp] = await Promise.all([
          getMarketView(),
          getSnapshot('pcr'),
          getSnapshot('vix'),
          getSnapshot('atm_oi'),
        ]);
        if (!active) return;
        setMarketView(parseMarketViewPayload(marketViewResp));
        setPcrData(getSnapshotData(pcrResp).data);
        setVixData(getSnapshotData(vixResp).data);
        setAtmData(getSnapshotData(atmResp).data);
      } catch (e: unknown) {
        if (!active) return;
        setError(e instanceof Error ? e.message : 'Failed to fetch live snapshots');
      }
    };
    fetchSnapshots();
    timer = window.setInterval(fetchSnapshots, 5000);
    return () => {
      active = false;
      if (timer != null) window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!selectedInstrument || !tickUpdatesEnabled) {
      setLiveTick(null);
      return;
    }
    let active = true;
    let timer: number | null = null;
    const fetchTick = async () => {
      try {
        const payload = await getLatestMarketTick(selectedInstrument.instrument_token);
        if (!active) return;
        const parsed = parseLiveTick(payload.tick);
        setLiveTick(parsed);
      } catch {
        if (!active) return;
      }
    };
    fetchTick();
    timer = window.setInterval(fetchTick, 1000);
    return () => {
      active = false;
      if (timer != null) window.clearInterval(timer);
    };
  }, [selectedInstrument, tickUpdatesEnabled]);

  useEffect(() => {
    if (!selectedInstrument || !selectedIndicators.length) {
      setIndicatorSeries([]);
      setIndicatorWarnings([]);
      return;
    }
    let active = true;
    const run = async () => {
      setIndicatorLoading(true);
      try {
        const resp = await computeIndicators({
          instrument_token: selectedInstrument.instrument_token,
          timeframe: primaryTimeframe,
          trading_date: selectedInstrument.trading_date,
          limit: 2500,
          indicators: selectedIndicators.map((x) => ({ name: x.name, params: x.params })),
        });
        if (!active) return;
        setIndicatorSeries(parseIndicatorSeries((resp as { series?: unknown }).series));
        setIndicatorWarnings(Array.isArray((resp as { warnings?: unknown }).warnings) ? ((resp as { warnings: string[] }).warnings) : []);
      } catch (e: unknown) {
        if (!active) return;
        setIndicatorWarnings([e instanceof Error ? e.message : 'Indicator compute failed']);
      } finally {
        if (active) setIndicatorLoading(false);
      }
    };
    run();
    return () => {
      active = false;
    };
  }, [primaryTimeframe, selectedInstrument, selectedIndicators]);

  const addIndicator = () => {
    const meta = indicatorMeta.find((x) => x.name === indicatorToAdd);
    if (!meta) return;
    const id = `${meta.name}-${Date.now()}`;
    setSelectedIndicators((prev) => [
      ...prev,
      {
        id,
        name: meta.name,
        label: meta.label,
        pane: meta.pane,
        params: defaultParamsFor(meta),
      },
    ]);
    setIndicatorToAdd('');
  };

  const toggleOverlayTimeframe = (tf: LiveTimeframe) => {
    if (tf === primaryTimeframe) return;
    setOverlayTimeframes((prev) =>
      prev.includes(tf) ? prev.filter((x) => x !== tf) : [...prev, tf].slice(0, 4),
    );
  };

  const updateIndicatorParam = (id: string, key: string, value: string) => {
    setSelectedIndicators((prev) =>
      prev.map((item) => {
        if (item.id !== id) return item;
        const meta = indicatorMeta.find((x) => x.name === item.name);
        const paramMeta = meta?.params?.find((p) => p.name === key);
        if (paramMeta?.type === 'number') {
          const parsed = Number(value);
          return { ...item, params: { ...item.params, [key]: Number.isFinite(parsed) ? parsed : item.params[key] } };
        }
        if (paramMeta?.type === 'boolean') {
          return { ...item, params: { ...item.params, [key]: value === 'true' } };
        }
        return { ...item, params: { ...item.params, [key]: value } };
      }),
    );
  };

  const removeIndicator = (id: string) => {
    setSelectedIndicators((prev) => prev.filter((x) => x.id !== id));
  };

  const collector = asObj(collectorStatus.collector);
  const calculator = asObj(collectorStatus.calculator);
  const currentVix = asNum(vixData.vix);
  const currentPcr = effectiveUnderlying === 'NIFTY' ? asNum(pcrData.nifty_pcr) : asNum(pcrData.banknifty_pcr);
  const collectorLastTick = asText(collector.last_tick_at);
  const collectorLastBar = asText(collector.last_bar_at);
  const collectorBarsWritten = asNum(collector.bars_written);
  const collectorTokens = asNum(collector.tokens_subscribed);

  const filterInstrumentTypes = useMemo(() => {
    const raw = asObj(inventoryFilterMeta);
    const values = Array.isArray(raw.instrument_types) ? raw.instrument_types : [];
    return values.map((x) => String(x));
  }, [inventoryFilterMeta]);
  const filterUnderlyings = useMemo(() => {
    const raw = asObj(inventoryFilterMeta);
    const values = Array.isArray(raw.underlyings) ? raw.underlyings : [];
    return values.map((x) => String(x));
  }, [inventoryFilterMeta]);
  const filterExpiries = useMemo(() => {
    const raw = asObj(inventoryFilterMeta);
    const values = Array.isArray(raw.expiries) ? raw.expiries : [];
    return values.map((x) => String(x));
  }, [inventoryFilterMeta]);
  const filterTradingDates = useMemo(() => {
    const raw = asObj(inventoryFilterMeta);
    const values = Array.isArray(raw.trading_dates) ? raw.trading_dates : [];
    return values.map((x) => String(x));
  }, [inventoryFilterMeta]);
  const filterTimeframes = useMemo(() => {
    const raw = asObj(inventoryFilterMeta);
    const values = Array.isArray(raw.timeframes) ? raw.timeframes : [];
    const cleaned = values.map((x) => String(x)).filter(Boolean);
    return cleaned.length ? cleaned : ['1min'];
  }, [inventoryFilterMeta]);

  return (
    <div className="animate-in continuous-page">
      <div className="card" style={{ marginBottom: 'var(--space-lg)' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 'var(--space-sm)' }}>
          <div>
            <label className="stat-label">Search Symbol/Token</label>
            <input className="input" value={filters.q} onChange={(e) => setFilters((p) => ({ ...p, q: e.target.value }))} placeholder="e.g. NIFTY, RELIANCE, 256265" />
          </div>
          <div>
            <label className="stat-label">Instrument Type</label>
            <select value={filters.instrumentType} onChange={(e) => setFilters((p) => ({ ...p, instrumentType: e.target.value }))}>
              <option value="all">All</option>
              {filterInstrumentTypes.map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          </div>
          <div>
            <label className="stat-label">Active Only</label>
            <select value={filters.activeOnly ? 'yes' : 'no'} onChange={(e) => setFilters((p) => ({ ...p, activeOnly: e.target.value === 'yes' }))}>
              <option value="yes">Yes</option>
              <option value="no">Include Stale</option>
            </select>
          </div>
          <div>
            <label className="stat-label">Underlying</label>
            <select value={filters.underlying} onChange={(e) => setFilters((p) => ({ ...p, underlying: e.target.value }))}>
              <option value="all">All</option>
              {filterUnderlyings.map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          </div>
          <div>
            <label className="stat-label">Expiry</label>
            <select value={filters.expiry} onChange={(e) => setFilters((p) => ({ ...p, expiry: e.target.value }))}>
              <option value="all">All</option>
              {filterExpiries.map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          </div>
          <div>
            <label className="stat-label">Timeframe</label>
            <select value={filters.timeframe} onChange={(e) => setFilters((p) => ({ ...p, timeframe: e.target.value }))}>
              {filterTimeframes.map((tf) => <option key={tf} value={tf}>{tf}</option>)}
              <option value="all">All</option>
            </select>
          </div>
          <div>
            <label className="stat-label">Trading Date</label>
            <select value={filters.tradingDate} onChange={(e) => setFilters((p) => ({ ...p, tradingDate: e.target.value }))}>
              <option value="">Latest</option>
              {filterTradingDates.map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          </div>
          <div>
            <Tooltip
              delayMs={2000}
              content="Primary timeframe drives the main candles and indicator calculations. Changing it switches aggregation source and can affect signal sensitivity."
            >
              <label className="stat-label">Primary Timeframe</label>
            </Tooltip>
            <select value={primaryTimeframe} onChange={(e) => setPrimaryTimeframe(e.target.value as LiveTimeframe)}>
              {LIVE_TIMEFRAMES.map((tf) => <option key={tf} value={tf}>{tf}</option>)}
            </select>
          </div>
          <div>
            <Tooltip
              delayMs={2000}
              content="Tick updates only modify the in-progress candle visually. Persisted bars remain candle-based in backend storage."
            >
              <label className="stat-label">Tick Visual Updates</label>
            </Tooltip>
            <select value={tickUpdatesEnabled ? 'on' : 'off'} onChange={(e) => setTickUpdatesEnabled(e.target.value === 'on')}>
              <option value="on">On</option>
              <option value="off">Off</option>
            </select>
          </div>
          <div>
            <Tooltip
              delayMs={2000}
              content="Auto-scroll keeps the chart pinned to latest bars when new tick/candle updates arrive."
            >
              <label className="stat-label">Auto Scroll</label>
            </Tooltip>
            <select value={autoScrollEnabled ? 'on' : 'off'} onChange={(e) => setAutoScrollEnabled(e.target.value === 'on')}>
              <option value="on">On</option>
              <option value="off">Off</option>
            </select>
          </div>
          <div>
            <SearchableDropdown
              label="Live Instrument"
              value={selectedInstrumentKey}
              options={inventoryOptions}
              onChange={setSelectedInstrumentKey}
              placeholder="Search selected inventory..."
              tooltipContent="Choose the instrument plotted on the chart. Selection drives bar fetches, live tick refresh, indicator computation, and option-chain context."
            />
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4 }}>
              <input
                id="show-options-in-dropdown"
                type="checkbox"
                checked={showOptionsInDropdown}
                onChange={(e) => setShowOptionsInDropdown(e.target.checked)}
              />
              <label htmlFor="show-options-in-dropdown" className="stat-label" style={{ cursor: 'pointer', margin: 0 }}>
                Include options in chart selector
              </label>
            </div>
          </div>
        </div>
        <div style={{ marginTop: 10 }}>
          <Tooltip
            delayMs={2000}
            content="Overlay additional timeframes on the same chart for context. Overlays are derived on demand from 1min base data and increase API/chart load."
          >
            <div className="stat-label" style={{ marginBottom: 6 }}>Overlay Timeframes</div>
          </Tooltip>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {LIVE_TIMEFRAMES.filter((tf) => tf !== primaryTimeframe).map((tf) => (
              <label key={`overlay-${tf}`} className="badge badge-neutral" style={{ cursor: 'pointer', gap: 6, padding: '4px 10px' }}>
                <input
                  type="checkbox"
                  checked={overlayTimeframes.includes(tf)}
                  onChange={() => toggleOverlayTimeframe(tf)}
                />
                {tf}
              </label>
            ))}
            {!!overlayTimeframes.length && (
              <button className="btn btn-ghost btn-sm" onClick={() => setOverlayTimeframes([])}>
                Clear Overlays
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 'var(--space-lg)' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr auto', gap: 'var(--space-sm)', alignItems: 'end' }}>
          <SearchableDropdown
            label="Add Indicator"
            value={indicatorToAdd}
            options={indicatorOptions}
            onChange={setIndicatorToAdd}
            placeholder="Search indicators..."
            tooltipContent="Select a pandas-ta indicator to compute on backend. Indicator parameters and primary timeframe affect compute cost and signal shape."
          />
          <div>
            <label className="stat-label">Option Scope</label>
            <select value={underlyingMode} onChange={(e) => setUnderlyingMode(e.target.value as UnderlyingMode)}>
              <option value="AUTO">Auto</option>
              <option value="NIFTY">NIFTY</option>
              <option value="BANKNIFTY">BANKNIFTY</option>
            </select>
          </div>
          <button className="btn btn-primary btn-sm" onClick={addIndicator} disabled={!indicatorToAdd}>Add Indicator</button>
        </div>
        {!!selectedIndicators.length && (
          <div style={{ marginTop: 10, display: 'grid', gap: 10 }}>
            {selectedIndicators.map((item) => {
              const meta = indicatorMeta.find((x) => x.name === item.name);
              return (
                <div key={item.id} style={{ border: '1px solid var(--border-subtle)', borderRadius: 8, padding: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                    <strong>{item.label}</strong>
                    <button className="btn btn-ghost btn-sm" onClick={() => removeIndicator(item.id)}>Remove</button>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 8, marginTop: 8 }}>
                    {(meta?.params || []).map((param) => (
                      <label key={`${item.id}-${param.name}`} style={{ display: 'grid', gap: 4 }}>
                        <span className="stat-label">{param.name}</span>
                        <input
                          className="input"
                          value={String(item.params[param.name] ?? '')}
                          onChange={(e) => updateIndicatorParam(item.id, param.name, e.target.value)}
                        />
                      </label>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
        {indicatorLoading ? <div style={{ marginTop: 8, color: 'var(--text-muted)' }}>Computing indicators...</div> : null}
        {indicatorWarnings.map((w, idx) => (
          <div key={`ind-warning-${idx}`} style={{ marginTop: 6, color: '#92400e', fontSize: '0.82rem' }}>{w}</div>
        ))}
      </div>

      <div
        className="grid"
        style={{ marginBottom: 'var(--space-lg)', gridTemplateColumns: 'minmax(0, 7fr) minmax(320px, 3fr)', gap: '16px' }}
      >
        <div className="card">
          {error ? <div className="badge badge-danger" style={{ marginBottom: 'var(--space-sm)' }}>Error: {error}</div> : null}
          {loadingBars && !bars.length ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-sm)' }}>
              <span className="spinner" />
              <span style={{ color: 'var(--text-secondary)' }}>Loading chart...</span>
            </div>
          ) : (
            <LightweightCandlestickChart
              bars={bars}
              symbol={selectedInstrument?.tradingsymbol ?? 'Live Instrument'}
              overlays={overlaySeries}
              candleOverlays={timeframeCandleOverlays}
              onCrosshairTime={setCrosshairTime}
              autoScroll={autoScrollEnabled}
            />
          )}
          <div style={{ marginTop: 8, fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Loaded bars: {bars.length} | Last tick: {formatIsoIst(collectorLastTick)} | Last bar: {formatIsoIst(collectorLastBar)}
          </div>
        </div>
        <div className="card">
          <div className="card-header">
            <span className="card-title">Option Chain ({effectiveUnderlying})</span>
            <div style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}>
              <select value={selectedChainExpiry} onChange={(e) => setSelectedChainExpiry(e.target.value)} style={{ width: 150 }}>
                <option value="ALL">All Expiries</option>
                {chainExpiries.map((x) => <option key={x} value={x}>{x}</option>)}
              </select>
              <span className="badge badge-info">{optionRowsVisible.length} strikes</span>
            </div>
          </div>
          <div className="table-wrapper" style={{ maxHeight: 430, overflow: 'auto' }}>
            <table>
              <thead>
                <tr>
                  <th>Strike</th>
                  <th>CE LTP</th>
                  <th>CE OI</th>
                  <th>PE LTP</th>
                  <th>PE OI</th>
                  <th>PCR</th>
                </tr>
              </thead>
              <tbody>
                {optionRowsVisible.map((row) => (
                  <tr key={`${row.strike}-${row.expiry || 'na'}`} style={row.strike === focusedStrike ? { background: 'rgba(14,165,233,0.12)' } : undefined}>
                    <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 700 }}>{row.strike}</td>
                    <td style={{ color: 'var(--red)', fontFamily: 'var(--font-mono)' }}>{row.ce_ltp.toFixed(2)}</td>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{Math.round(row.ce_oi).toLocaleString()}</td>
                    <td style={{ color: 'var(--green)', fontFamily: 'var(--font-mono)' }}>{row.pe_ltp.toFixed(2)}</td>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{Math.round(row.pe_oi).toLocaleString()}</td>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{row.strike_pcr != null ? row.strike_pcr.toFixed(4) : '--'}</td>
                  </tr>
                ))}
                {!optionRowsVisible.length && (
                  <tr>
                    <td colSpan={6} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>Option chain data unavailable</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="grid grid-4" style={{ marginBottom: 'var(--space-lg)' }}>
        <div className="card"><div className="stat-label">Collector</div><div className="stat-value neutral">{asText(collector.status) || '--'}</div></div>
        <div className="card"><div className="stat-label">Calculator</div><div className="stat-value neutral">{asText(calculator.status) || '--'}</div></div>
        <div className="card"><div className="stat-label">Tokens Subscribed</div><div className="stat-value neutral">{collectorTokens ?? '--'}</div></div>
        <div className="card"><div className="stat-label">Bars Written</div><div className="stat-value neutral">{collectorBarsWritten ?? '--'}</div></div>
      </div>

      <div className="grid grid-2" style={{ marginBottom: 'var(--space-lg)' }}>
        <div className="card">
          <div className="card-header">
            <span className="card-title">Market View</span>
          </div>
          {(['NIFTY', 'BANKNIFTY'] as const).map((underlying) => {
            const side = marketView.market_view[underlying];
            const spotPrice = side?.spot?.price ?? null;
            const futures = Array.isArray(side?.futures) ? side.futures : [];
            return (
              <div key={`mv-${underlying}`} style={{ marginBottom: 12 }}>
                <div className="stat-label" style={{ marginBottom: 4 }}>{underlying}</div>
                <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.max(2, futures.length + 1)}, minmax(0, 1fr))`, gap: 8 }}>
                  <div style={{ background: 'var(--bg-subtle)', borderRadius: 6, padding: '6px 10px' }}>
                    <div className="stat-label">Spot</div>
                    <div className="stat-value neutral" style={{ fontSize: '1rem' }}>
                      {spotPrice != null ? spotPrice.toFixed(2) : '--'}
                    </div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{side?.spot?.tradingsymbol || '--'}</div>
                  </div>
                  {futures.map((future: (typeof side.futures)[number], idx: number) => {
                    const basis = basisFromSpotAndFuture(spotPrice, future.price);
                    return (
                      <div key={`mv-${underlying}-${idx}`} style={{ background: 'var(--bg-subtle)', borderRadius: 6, padding: '6px 10px' }}>
                        <div className="stat-label">{idx === 0 ? 'Current Fut' : 'Next Fut'}</div>
                        <div className="stat-value neutral" style={{ fontSize: '1rem' }}>
                          {future.price != null ? future.price.toFixed(2) : '--'}
                        </div>
                        <div
                          style={{
                            fontSize: '0.72rem',
                            color: basis == null ? 'var(--text-muted)' : basis >= 0 ? 'var(--green)' : 'var(--red)',
                          }}
                        >
                          {basis != null ? `${basis >= 0 ? '+' : ''}${basis.toFixed(2)} basis` : '--'}
                        </div>
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{future.expiry || '--'}</div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
        <div className="card">
          <div className="card-header">
            <span className="card-title">Pulse Metrics</span>
            <span className="badge badge-info">{effectiveUnderlying}</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 'var(--space-sm)' }}>
            <div><div className="stat-label">PCR</div><div className="stat-value neutral">{currentPcr != null ? currentPcr.toFixed(4) : '--'}</div></div>
            <div><div className="stat-label">VIX</div><div className="stat-value neutral">{currentVix != null ? currentVix.toFixed(2) : '--'}</div></div>
            <div><div className="stat-label">ATM Strike</div><div className="stat-value neutral">{atmStrike ?? '--'}</div></div>
          </div>
          {asText(atmData.warning) ? (
            <div style={{ marginTop: 8, fontSize: '0.8rem', color: '#92400e' }}>{asText(atmData.warning)}</div>
          ) : null}
        </div>
      </div>

      {!!oscillatorSeries.length && (
        <div className="card" style={{ marginBottom: 'var(--space-lg)' }}>
          <LightweightLineChart title="Oscillator Indicators" series={oscillatorSeries} />
        </div>
      )}

      <div style={{ marginTop: 'var(--space-md)', color: 'var(--text-muted)', fontSize: '0.8rem' }}>
        Last update: {lastUpdate ? formatIsoIst(lastUpdate) : '--'}
        {selectedInstrument ? ` | Selected: ${selectedInstrument.tradingsymbol} (${selectedInstrument.instrument_token}) ${selectedInstrument.timeframe} ${selectedInstrument.trading_date}` : ''}
        {selectedInstrument?.is_active != null ? ` | Active: ${selectedInstrument.is_active ? 'Yes' : 'Stale'}` : ''}
        {selectedInstrument?.stale_seconds != null ? ` | Stale age: ${selectedInstrument.stale_seconds}s` : ''}
      </div>
    </div>
  );
}
