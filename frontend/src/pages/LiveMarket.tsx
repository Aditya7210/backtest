import { useEffect, useMemo, useState } from 'react';
import LightweightCandlestickChart from '../components/LightweightCandlestickChart';
import LightweightLineChart, { type LinePoint } from '../components/LightweightLineChart';
import PageMetaBar from '../components/PageMetaBar';
import { getCatalog, getMarketBars, getSnapshot } from '../services/api';
import type { OHLCVBar } from '../types/market';

interface CatalogTimeframe {
  timeframe: string;
  date_from: string;
  date_to: string;
  total_bars: number;
}

interface CatalogInstrument {
  instrument_token: number;
  tradingsymbol: string;
  timeframes_available?: CatalogTimeframe[];
}

interface AdStats {
  advances: number;
  declines: number;
  ad_ratio: number;
}

interface OptionChainRow {
  strike: number;
  expiry?: string;
  ce_ltp: number;
  pe_ltp: number;
  ce_oi: number;
  pe_oi: number;
  strike_pcr: number;
}

type UnderlyingMode = 'AUTO' | 'NIFTY' | 'BANKNIFTY';

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
}

function asNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string') {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function toUnixSeconds(value: unknown): number | null {
  if (typeof value !== 'string' || !value) return null;
  const millis = Date.parse(value);
  return Number.isFinite(millis) ? Math.floor(millis / 1000) : null;
}

function parseBars(value: unknown): OHLCVBar[] {
  if (!Array.isArray(value)) return [];
  const parsed: OHLCVBar[] = [];
  for (const row of value) {
    const record = asRecord(row);
    const time = asNumber(record.time);
    const open = asNumber(record.open);
    const high = asNumber(record.high);
    const low = asNumber(record.low);
    const close = asNumber(record.close);
    const volume = asNumber(record.volume) ?? 0;
    if (time == null || open == null || high == null || low == null || close == null) continue;
    parsed.push({ time, open, high, low, close, volume });
  }
  return parsed.sort((a, b) => a.time - b.time);
}

function parseCatalog(value: unknown): CatalogInstrument[] {
  if (!Array.isArray(value)) return [];
  const parsed: CatalogInstrument[] = [];
  for (const row of value) {
    const record = asRecord(row);
    const token = asNumber(record.instrument_token);
    const symbol = typeof record.tradingsymbol === 'string' ? record.tradingsymbol : null;
    if (token == null || !symbol) continue;
    const tfRaw = Array.isArray(record.timeframes_available) ? record.timeframes_available : [];
    const timeframes_available: CatalogTimeframe[] = tfRaw
      .map((entry) => {
        const tfRec = asRecord(entry);
        const timeframe = typeof tfRec.timeframe === 'string' ? tfRec.timeframe : null;
        const date_from = typeof tfRec.date_from === 'string' ? tfRec.date_from : '';
        const date_to = typeof tfRec.date_to === 'string' ? tfRec.date_to : '';
        const total_bars = asNumber(tfRec.total_bars) ?? 0;
        if (!timeframe) return null;
        return { timeframe, date_from, date_to, total_bars };
      })
      .filter((x): x is CatalogTimeframe => x !== null);
    parsed.push({ instrument_token: token, tradingsymbol: symbol, timeframes_available });
  }
  return parsed;
}

function pickDefaultInstrument(catalog: CatalogInstrument[]): CatalogInstrument | null {
  if (!catalog.length) return null;
  const preferred = ['NIFTY 50', 'NIFTY', 'NIFTY BANK', 'BANKNIFTY'];
  for (const needle of preferred) {
    const found = catalog.find((x) => x.tradingsymbol.toUpperCase().includes(needle));
    if (found) return found;
  }
  return catalog[0];
}

function appendPoint(history: LinePoint[], next: LinePoint, max = 300): LinePoint[] {
  if (!Number.isFinite(next.value)) return history;
  if (history.length && history[history.length - 1].time === next.time) {
    const updated = history.slice();
    updated[updated.length - 1] = next;
    return updated;
  }
  const appended = [...history, next];
  return appended.length > max ? appended.slice(appended.length - max) : appended;
}

function computeSMA(bars: OHLCVBar[], period: number): LinePoint[] {
  const out: LinePoint[] = [];
  if (!bars.length || period <= 1) {
    return bars.map((b) => ({ time: b.time, value: b.close }));
  }
  let sum = 0;
  for (let i = 0; i < bars.length; i += 1) {
    sum += bars[i].close;
    if (i >= period) sum -= bars[i - period].close;
    if (i >= period - 1) out.push({ time: bars[i].time, value: sum / period });
  }
  return out;
}

function computeVWAP(bars: OHLCVBar[]): LinePoint[] {
  const out: LinePoint[] = [];
  let cumulativePV = 0;
  let cumulativeVolume = 0;
  for (const bar of bars) {
    const typical = (bar.high + bar.low + bar.close) / 3;
    cumulativePV += typical * bar.volume;
    cumulativeVolume += bar.volume;
    if (cumulativeVolume > 0) out.push({ time: bar.time, value: cumulativePV / cumulativeVolume });
  }
  return out;
}

function computeRSI(bars: OHLCVBar[], period = 14): LinePoint[] {
  if (bars.length < period + 1) return [];
  const out: LinePoint[] = [];
  let gains = 0;
  let losses = 0;
  for (let i = 1; i <= period; i += 1) {
    const delta = bars[i].close - bars[i - 1].close;
    if (delta >= 0) gains += delta;
    else losses += Math.abs(delta);
  }
  let avgGain = gains / period;
  let avgLoss = losses / period;
  const firstRs = avgLoss === 0 ? 100 : avgGain / avgLoss;
  out.push({ time: bars[period].time, value: 100 - 100 / (1 + firstRs) });

  for (let i = period + 1; i < bars.length; i += 1) {
    const delta = bars[i].close - bars[i - 1].close;
    const gain = delta > 0 ? delta : 0;
    const loss = delta < 0 ? Math.abs(delta) : 0;
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
    const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
    out.push({ time: bars[i].time, value: 100 - 100 / (1 + rs) });
  }
  return out;
}

function getSnapshotData(payload: unknown): { data: Record<string, unknown>; generatedAt: number | null } {
  const root = asRecord(payload);
  const nested = asRecord(root.data);
  const data = Object.keys(nested).length ? nested : root;
  const generatedAt = toUnixSeconds(root.generated_at) ?? toUnixSeconds(data.generated_at);
  return { data, generatedAt };
}

function inferUnderlying(symbol: string): 'NIFTY' | 'BANKNIFTY' {
  const up = symbol.toUpperCase();
  if (up.includes('BANK')) return 'BANKNIFTY';
  return 'NIFTY';
}

function getAdStats(data: Record<string, unknown>, universe: string): AdStats | null {
  const universes = asRecord(data.universes);
  const preferred = asRecord(universes[universe]);
  const fallback = data;
  const advances = asNumber(preferred.advances) ?? asNumber(fallback.advances);
  const declines = asNumber(preferred.declines) ?? asNumber(fallback.declines);
  const adRatio = asNumber(preferred.ad_ratio) ?? asNumber(fallback.ad_ratio);
  if (advances == null || declines == null || adRatio == null) return null;
  return { advances, declines, ad_ratio: adRatio };
}

function parseOptionRows(pcrData: Record<string, unknown>, underlying: 'NIFTY' | 'BANKNIFTY'): OptionChainRow[] {
  const chainRoot = asRecord(pcrData.option_chain);
  const rowsRaw = Array.isArray(chainRoot[underlying]) ? chainRoot[underlying] : [];
  const rows: OptionChainRow[] = [];
  for (const row of rowsRaw) {
    const rec = asRecord(row);
    const strike = asNumber(rec.strike);
    const ceLtp = asNumber(rec.ce_ltp);
    const peLtp = asNumber(rec.pe_ltp);
    const ceOi = asNumber(rec.ce_oi);
    const peOi = asNumber(rec.pe_oi);
    const strikePcr = asNumber(rec.strike_pcr) ?? 0;
    if (strike == null || ceLtp == null || peLtp == null || ceOi == null || peOi == null) continue;
    rows.push({
      strike,
      expiry: typeof rec.expiry === 'string' ? rec.expiry : undefined,
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

function pctFromBaseline(current: number, baseline: number | null): number | null {
  if (baseline == null || baseline <= 0) return null;
  return ((current - baseline) / baseline) * 100;
}

export default function LiveMarket() {
  const [catalog, setCatalog] = useState<CatalogInstrument[]>([]);
  const [selectedToken, setSelectedToken] = useState<number | null>(null);
  const [selectedTimeframe, setSelectedTimeframe] = useState('1min');
  const [bars, setBars] = useState<OHLCVBar[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<string | null>(null);
  const [crosshairTime, setCrosshairTime] = useState<number | null>(null);

  const [adData, setAdData] = useState<Record<string, unknown>>({});
  const [pcrData, setPcrData] = useState<Record<string, unknown>>({});
  const [vixData, setVixData] = useState<Record<string, unknown>>({});
  const [adUniverseOptions, setAdUniverseOptions] = useState<string[]>([]);
  const [selectedAdUniverse, setSelectedAdUniverse] = useState('NIFTY 50');
  const [underlyingMode, setUnderlyingMode] = useState<UnderlyingMode>('AUTO');

  const [adAdvHistory, setAdAdvHistory] = useState<LinePoint[]>([]);
  const [adDecHistory, setAdDecHistory] = useState<LinePoint[]>([]);
  const [niftyPcrHistory, setNiftyPcrHistory] = useState<LinePoint[]>([]);
  const [bankPcrHistory, setBankPcrHistory] = useState<LinePoint[]>([]);
  const [callOiHistory, setCallOiHistory] = useState<LinePoint[]>([]);
  const [putOiHistory, setPutOiHistory] = useState<LinePoint[]>([]);
  const [straddleHistory, setStraddleHistory] = useState<LinePoint[]>([]);
  const [vixHistory, setVixHistory] = useState<LinePoint[]>([]);
  const [oiBaseline, setOiBaseline] = useState<Record<string, { ce: number; pe: number }>>({});

  const selectedInstrument = useMemo(
    () => catalog.find((x) => x.instrument_token === selectedToken) ?? null,
    [catalog, selectedToken],
  );

  const availableTimeframes = useMemo(() => {
    const set = new Set<string>();
    for (const tf of selectedInstrument?.timeframes_available ?? []) set.add(tf.timeframe);
    if (!set.size) set.add('1min');
    return Array.from(set);
  }, [selectedInstrument]);

  const selectedDate = useMemo(() => {
    if (!selectedInstrument) return undefined;
    const tfMeta = (selectedInstrument.timeframes_available ?? []).find((x) => x.timeframe === selectedTimeframe);
    return tfMeta?.date_to;
  }, [selectedInstrument, selectedTimeframe]);

  const effectiveUnderlying = useMemo<'NIFTY' | 'BANKNIFTY'>(() => {
    if (underlyingMode === 'NIFTY') return 'NIFTY';
    if (underlyingMode === 'BANKNIFTY') return 'BANKNIFTY';
    return inferUnderlying(selectedInstrument?.tradingsymbol ?? 'NIFTY');
  }, [underlyingMode, selectedInstrument]);

  const optionRows = useMemo(
    () => parseOptionRows(pcrData, effectiveUnderlying),
    [pcrData, effectiveUnderlying],
  );

  const spot = bars.length ? bars[bars.length - 1].close : null;
  const atmStrike = useMemo(() => {
    if (!spot) return null;
    return nearestStrike(optionRows.map((r) => r.strike), spot);
  }, [spot, optionRows]);

  const focusedStrike = useMemo(() => {
    if (!crosshairTime || !optionRows.length) return atmStrike;
    const bar = bars.find((b) => b.time === crosshairTime);
    if (!bar) return atmStrike;
    return nearestStrike(optionRows.map((r) => r.strike), bar.close);
  }, [crosshairTime, optionRows, bars, atmStrike]);

  const visibleChain = useMemo(() => {
    if (!optionRows.length) return [];
    const center = focusedStrike ?? optionRows[Math.floor(optionRows.length / 2)]?.strike ?? optionRows[0].strike;
    return optionRows
      .slice()
      .sort((a, b) => Math.abs(a.strike - center) - Math.abs(b.strike - center))
      .slice(0, 24)
      .sort((a, b) => a.strike - b.strike);
  }, [optionRows, focusedStrike]);

  useEffect(() => {
    let active = true;
    getCatalog()
      .then((resp) => {
        if (!active) return;
        const parsed = parseCatalog((resp as { catalog?: unknown }).catalog);
        setCatalog(parsed);
        const defaultInstrument = pickDefaultInstrument(parsed);
        if (defaultInstrument) {
          setSelectedToken(defaultInstrument.instrument_token);
          const tfs = defaultInstrument.timeframes_available ?? [];
          if (tfs.some((x) => x.timeframe === '1min')) setSelectedTimeframe('1min');
          else if (tfs[0]?.timeframe) setSelectedTimeframe(tfs[0].timeframe);
        }
      })
      .catch((e: unknown) => {
        if (!active) return;
        setError(e instanceof Error ? e.message : 'Failed to load instrument catalog');
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedToken) return;
    let active = true;
    let timer: number | null = null;

    const fetchBars = async () => {
      setLoading(true);
      try {
        const resp = await getMarketBars(selectedToken, selectedTimeframe, selectedDate);
        if (!active) return;
        const nextBars = parseBars((resp as { bars?: unknown }).bars);
        setBars(nextBars);
        setError(null);
        setLastUpdate(new Date().toISOString());
      } catch (e: unknown) {
        if (!active) return;
        setError(e instanceof Error ? e.message : 'Failed to fetch live bars');
      } finally {
        if (active) setLoading(false);
      }
    };

    fetchBars();
    timer = window.setInterval(fetchBars, 5000);
    return () => {
      active = false;
      if (timer != null) window.clearInterval(timer);
    };
  }, [selectedToken, selectedTimeframe, selectedDate]);

  useEffect(() => {
    let active = true;
    let timer: number | null = null;

    const fetchSnapshots = async () => {
      try {
        const [adResp, pcrResp, vixResp] = await Promise.all([
          getSnapshot('ad'),
          getSnapshot('pcr'),
          getSnapshot('vix'),
        ]);
        if (!active) return;

        const adParsed = getSnapshotData(adResp);
        const pcrParsed = getSnapshotData(pcrResp);
        const vixParsed = getSnapshotData(vixResp);
        setAdData(adParsed.data);
        setPcrData(pcrParsed.data);
        setVixData(vixParsed.data);

        const universes = Object.keys(asRecord(adParsed.data.universes));
        if (universes.length) {
          setAdUniverseOptions(universes);
          if (!universes.includes(selectedAdUniverse)) {
            setSelectedAdUniverse(universes[0]);
          }
        }

        const adStats = getAdStats(adParsed.data, selectedAdUniverse);
        const tAd = adParsed.generatedAt;
        if (adStats && tAd != null) {
          setAdAdvHistory((prev) => appendPoint(prev, { time: tAd, value: adStats.advances }));
          setAdDecHistory((prev) => appendPoint(prev, { time: tAd, value: adStats.declines }));
        }

        const tPcr = pcrParsed.generatedAt;
        const niftyPcr = asNumber(pcrParsed.data.nifty_pcr);
        const bankPcr = asNumber(pcrParsed.data.banknifty_pcr);
        if (tPcr != null && niftyPcr != null) {
          setNiftyPcrHistory((prev) => appendPoint(prev, { time: tPcr, value: niftyPcr }));
        }
        if (tPcr != null && bankPcr != null) {
          setBankPcrHistory((prev) => appendPoint(prev, { time: tPcr, value: bankPcr }));
        }

        const tVix = vixParsed.generatedAt;
        const vix = asNumber(vixParsed.data.vix);
        if (tVix != null && vix != null) {
          setVixHistory((prev) => appendPoint(prev, { time: tVix, value: vix }));
        }

        const underlying = effectiveUnderlying;
        const chainRows = parseOptionRows(pcrParsed.data, underlying);
        if (chainRows.length && tPcr != null) {
          const spotRef = spot ?? bars[bars.length - 1]?.close ?? chainRows[Math.floor(chainRows.length / 2)].strike;
          const atm = nearestStrike(chainRows.map((r) => r.strike), spotRef);
          const atmRow = chainRows.find((r) => r.strike === atm) ?? null;
          if (atmRow) {
            setStraddleHistory((prev) => appendPoint(prev, { time: tPcr, value: atmRow.ce_ltp + atmRow.pe_ltp }));
          }
        }

        if (tPcr != null) {
          if (underlying === 'NIFTY') {
            const callOi = asNumber(pcrParsed.data.nifty_call_oi);
            const putOi = asNumber(pcrParsed.data.nifty_put_oi);
            if (callOi != null) setCallOiHistory((prev) => appendPoint(prev, { time: tPcr, value: callOi }));
            if (putOi != null) setPutOiHistory((prev) => appendPoint(prev, { time: tPcr, value: putOi }));
          } else {
            const callOi = asNumber(pcrParsed.data.banknifty_call_oi);
            const putOi = asNumber(pcrParsed.data.banknifty_put_oi);
            if (callOi != null) setCallOiHistory((prev) => appendPoint(prev, { time: tPcr, value: callOi }));
            if (putOi != null) setPutOiHistory((prev) => appendPoint(prev, { time: tPcr, value: putOi }));
          }
        }
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
  }, [bars, effectiveUnderlying, selectedAdUniverse, spot]);

  useEffect(() => {
    if (!optionRows.length) return;
    setOiBaseline((prev) => {
      const next = { ...prev };
      for (const row of optionRows) {
        const key = `${effectiveUnderlying}:${row.strike}`;
        if (!next[key]) next[key] = { ce: row.ce_oi, pe: row.pe_oi };
      }
      return next;
    });
  }, [optionRows, effectiveUnderlying]);

  const sma5 = useMemo(() => computeSMA(bars, 5), [bars]);
  const sma20 = useMemo(() => computeSMA(bars, 20), [bars]);
  const sma50 = useMemo(() => computeSMA(bars, 50), [bars]);
  const vwap = useMemo(() => computeVWAP(bars), [bars]);
  const rsi14 = useMemo(() => computeRSI(bars, 14), [bars]);

  const candleOverlays = useMemo(
    () => [
      { key: 'sma5', label: 'SMA 5', color: '#2563EB', data: sma5 },
      { key: 'sma20', label: 'SMA 20', color: '#F59E0B', data: sma20 },
      { key: 'sma50', label: 'SMA 50', color: '#A855F7', data: sma50 },
      { key: 'vwap', label: 'VWAP', color: '#0EA5E9', data: vwap },
    ],
    [sma5, sma20, sma50, vwap],
  );

  const adStats = useMemo(() => getAdStats(adData, selectedAdUniverse), [adData, selectedAdUniverse]);
  const lastBar = bars.length ? bars[bars.length - 1] : null;
  const currentVix = useMemo(() => asNumber(vixData.vix), [vixData]);
  const currentPcr = useMemo(() => {
    if (effectiveUnderlying === 'NIFTY') return asNumber(pcrData.nifty_pcr);
    return asNumber(pcrData.banknifty_pcr);
  }, [pcrData, effectiveUnderlying]);

  return (
    <div className="animate-in">
      <div className="page-header">
        <h1 className="page-title">Live Market</h1>
        <p className="page-subtitle">All live charts are rendered with TradingView Lightweight Charts</p>
        <PageMetaBar
          items={['TradingView Charts', 'Option Chain + OI', 'Indicator Overlays']}
          rightText="Auto refresh 5s"
        />
      </div>

      <div className="card" style={{ marginBottom: 'var(--space-lg)' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 'var(--space-md)' }}>
          <div>
            <label className="stat-label" htmlFor="instrument-select">Instrument</label>
            <select id="instrument-select" value={selectedToken ?? ''} onChange={(e) => setSelectedToken(Number(e.target.value))}>
              {catalog.map((inst) => (
                <option key={inst.instrument_token} value={inst.instrument_token}>
                  {inst.tradingsymbol} ({inst.instrument_token})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="stat-label" htmlFor="timeframe-select">Timeframe</label>
            <select id="timeframe-select" value={selectedTimeframe} onChange={(e) => setSelectedTimeframe(e.target.value)}>
              {availableTimeframes.map((tf) => (
                <option key={tf} value={tf}>{tf}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="stat-label" htmlFor="ad-filter-select">A/D Filter</label>
            <select id="ad-filter-select" value={selectedAdUniverse} onChange={(e) => setSelectedAdUniverse(e.target.value)}>
              {adUniverseOptions.map((u) => (
                <option key={u} value={u}>{u}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="stat-label" htmlFor="underlying-mode-select">Option Scope</label>
            <select id="underlying-mode-select" value={underlyingMode} onChange={(e) => setUnderlyingMode(e.target.value as UnderlyingMode)}>
              <option value="AUTO">Auto</option>
              <option value="NIFTY">NIFTY</option>
              <option value="BANKNIFTY">BANKNIFTY</option>
            </select>
          </div>
        </div>
      </div>

      <div className="grid grid-2" style={{ marginBottom: 'var(--space-lg)' }}>
        <div className="card">
          {error ? <div className="badge badge-danger" style={{ marginBottom: 'var(--space-sm)' }}>Error: {error}</div> : null}
          {loading && !bars.length ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-sm)' }}>
              <span className="spinner" />
              <span style={{ color: 'var(--text-secondary)' }}>Loading chart...</span>
            </div>
          ) : (
            <LightweightCandlestickChart
              bars={bars}
              symbol={selectedInstrument?.tradingsymbol ?? String(selectedToken ?? '')}
              overlays={candleOverlays}
              onCrosshairTime={setCrosshairTime}
            />
          )}
        </div>
        <div className="card">
          <div className="card-header">
            <span className="card-title">Option Chain ({effectiveUnderlying})</span>
            <span className="badge badge-info">{visibleChain.length} strikes</span>
          </div>
          <div className="table-wrapper" style={{ maxHeight: '430px', overflow: 'auto' }}>
            <table>
              <thead>
                <tr>
                  <th>CE OI</th>
                  <th>CE LTP</th>
                  <th>Strike</th>
                  <th>PE LTP</th>
                  <th>PE OI</th>
                  <th>OI Chg %</th>
                </tr>
              </thead>
              <tbody>
                {visibleChain.map((row) => {
                  const key = `${effectiveUnderlying}:${row.strike}`;
                  const base = oiBaseline[key];
                  const ceChg = pctFromBaseline(row.ce_oi, base?.ce ?? null);
                  const peChg = pctFromBaseline(row.pe_oi, base?.pe ?? null);
                  const highlight = row.strike === focusedStrike;
                  return (
                    <tr key={row.strike} style={highlight ? { background: 'rgba(14,165,233,0.12)' } : undefined}>
                      <td style={{ fontFamily: 'var(--font-mono)' }}>{Math.round(row.ce_oi).toLocaleString()}</td>
                      <td style={{ color: 'var(--red)', fontFamily: 'var(--font-mono)' }}>{row.ce_ltp.toFixed(2)}</td>
                      <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 700 }}>{row.strike}</td>
                      <td style={{ color: 'var(--green)', fontFamily: 'var(--font-mono)' }}>{row.pe_ltp.toFixed(2)}</td>
                      <td style={{ fontFamily: 'var(--font-mono)' }}>{Math.round(row.pe_oi).toLocaleString()}</td>
                      <td style={{ fontFamily: 'var(--font-mono)' }}>
                        <span style={{ color: ceChg != null && ceChg >= 0 ? 'var(--green)' : 'var(--red)' }}>
                          CE {ceChg != null ? `${ceChg.toFixed(1)}%` : '--'}
                        </span>
                        {' / '}
                        <span style={{ color: peChg != null && peChg >= 0 ? 'var(--green)' : 'var(--red)' }}>
                          PE {peChg != null ? `${peChg.toFixed(1)}%` : '--'}
                        </span>
                      </td>
                    </tr>
                  );
                })}
                {!visibleChain.length && (
                  <tr>
                    <td colSpan={6} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
                      Option chain data is not available for this scope.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="grid grid-4" style={{ marginBottom: 'var(--space-lg)' }}>
        <div className="card"><div className="stat-label">Open</div><div className="stat-value neutral">{lastBar ? lastBar.open.toFixed(2) : '--'}</div></div>
        <div className="card"><div className="stat-label">High</div><div className="stat-value positive">{lastBar ? lastBar.high.toFixed(2) : '--'}</div></div>
        <div className="card"><div className="stat-label">Low</div><div className="stat-value negative">{lastBar ? lastBar.low.toFixed(2) : '--'}</div></div>
        <div className="card"><div className="stat-label">Close</div><div className="stat-value neutral">{lastBar ? lastBar.close.toFixed(2) : '--'}</div></div>
      </div>

      <div className="grid grid-2" style={{ marginBottom: 'var(--space-lg)' }}>
        <div className="card">
          <LightweightLineChart
            title="Advance / Decline Trend"
            series={[
              { id: 'adv', label: 'Advances', color: '#14B8A6', data: adAdvHistory },
              { id: 'dec', label: 'Declines', color: '#EF4444', data: adDecHistory },
            ]}
          />
        </div>
        <div className="card">
          <LightweightLineChart
            title="PCR Trend"
            series={[
              { id: 'nifty-pcr', label: 'NIFTY PCR', color: '#2563EB', data: niftyPcrHistory },
              { id: 'bank-pcr', label: 'BANKNIFTY PCR', color: '#F59E0B', data: bankPcrHistory },
            ]}
          />
        </div>
      </div>

      <div className="grid grid-3">
        <div className="card">
          <LightweightLineChart
            title="RSI (14)"
            series={[{ id: 'rsi14', label: 'RSI', color: '#8B5CF6', data: rsi14 }]}
            height={220}
          />
        </div>
        <div className="card">
          <LightweightLineChart
            title={`ATM Straddle (${effectiveUnderlying})`}
            series={[{ id: 'atm-straddle', label: 'CE+PE', color: '#EC4899', data: straddleHistory }]}
            height={220}
          />
        </div>
        <div className="card">
          <LightweightLineChart
            title={`Call vs Put OI (${effectiveUnderlying})`}
            series={[
              { id: 'call-oi', label: 'Call OI', color: '#EF4444', data: callOiHistory },
              { id: 'put-oi', label: 'Put OI', color: '#14B8A6', data: putOiHistory },
              { id: 'vix', label: 'VIX', color: '#0EA5E9', data: vixHistory },
            ]}
            height={220}
          />
        </div>
      </div>

      <div style={{ marginTop: 'var(--space-md)', color: 'var(--text-muted)', fontSize: '0.8rem' }}>
        Last update: {lastUpdate ?? '--'}
        {selectedDate ? ` | Trading date: ${selectedDate}` : ''}
        {adStats ? ` | A/D (${selectedAdUniverse}): ${adStats.advances}/${adStats.declines} (${adStats.ad_ratio.toFixed(4)})` : ''}
        {currentPcr != null ? ` | ${effectiveUnderlying} PCR: ${currentPcr.toFixed(4)}` : ''}
        {currentVix != null ? ` | VIX: ${currentVix.toFixed(2)}` : ''}
      </div>
    </div>
  );
}
