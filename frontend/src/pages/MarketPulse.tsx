import { useCallback, useEffect, useMemo, useState } from 'react';
import { getCollectorStatus, getMarketView, getSnapshot, startCalculator, startCollector, stopCalculator, stopCollector } from '../services/api';
import { basisFromSpotAndFuture, parseMarketViewPayload, type MarketViewPayload } from '../features/live-market/marketView';
import Tooltip from '../components/Tooltip';
import TooltipLabel from '../components/TooltipLabel';

type Snapshot = Record<string, unknown>;

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

function parseSnapshot(payload: unknown): Snapshot {
  const root = asObj(payload);
  const nested = asObj(root.data);
  return Object.keys(nested).length ? nested : root;
}

export default function MarketPulsePage() {
  const [collectorStatus, setCollectorStatus] = useState<Record<string, unknown>>({});
  const [marketView, setMarketView] = useState<MarketViewPayload>({
    generated_at: null,
    market_view: { NIFTY: { spot: null, futures: [] }, BANKNIFTY: { spot: null, futures: [] } },
  });
  const [pcrSnapshot, setPcrSnapshot] = useState<Snapshot>({});
  const [vixSnapshot, setVixSnapshot] = useState<Snapshot>({});
  const [atmSnapshot, setAtmSnapshot] = useState<Snapshot>({});
  const [underlying, setUnderlying] = useState<'NIFTY' | 'BANKNIFTY'>('NIFTY');
  const [selectedExpiry, setSelectedExpiry] = useState<string>('ALL');
  const [error, setError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    try {
      const [status, marketViewResp, pcr, vix, atm] = await Promise.all([
        getCollectorStatus(),
        getMarketView(),
        getSnapshot('pcr'),
        getSnapshot('vix'),
        getSnapshot('atm_oi'),
      ]);
      setCollectorStatus(asObj(status));
      setMarketView(parseMarketViewPayload(marketViewResp));
      setPcrSnapshot(parseSnapshot(pcr));
      setVixSnapshot(parseSnapshot(vix));
      setAtmSnapshot(parseSnapshot(atm));
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load market pulse');
    }
  }, []);

  useEffect(() => {
    void fetchAll();
  }, [fetchAll]);

  useEffect(() => {
    let mounted = true;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const socket = new WebSocket(`${protocol}//${window.location.host}/ws/live`);

    socket.onmessage = (event) => {
      if (!mounted) return;
      try {
        const payload = asObj(JSON.parse(event.data) as unknown);
        if (payload.type !== 'snapshot_update') return;
        setPcrSnapshot(parseSnapshot(payload.pcr));
        setVixSnapshot(parseSnapshot(payload.vix));
        setAtmSnapshot(parseSnapshot(payload.atm_oi));
      } catch {
        // Ignore malformed payloads.
      }
    };
    socket.onerror = () => {
      if (mounted) setError((prev) => prev ?? 'Live stream connection issue. Showing latest loaded snapshot data.');
    };
    socket.onclose = () => {
      if (mounted) setError((prev) => prev ?? 'Live stream disconnected. Reload page to reconnect.');
    };

    return () => {
      mounted = false;
      socket.close();
    };
  }, []);

  const collector = asObj(collectorStatus.collector);
  const calculator = asObj(collectorStatus.calculator);
  const collectorFile = {
    ...asObj(collector),
    ...asObj(collectorStatus.collector_file_status),
  };
  const health = asObj(collectorStatus.collector_status_health);
  const snapshotHealth = asObj(collectorStatus.snapshot_health);

  const optionChainRows = useMemo(() => {
    const chainRoot = {
      ...asObj(pcrSnapshot.option_chain),
      ...asObj(atmSnapshot.option_chain),
    };
    const rows = chainRoot[underlying];
    return Array.isArray(rows) ? rows : [];
  }, [atmSnapshot, pcrSnapshot, underlying]);

  const chainExpiries = useMemo(
    () =>
      Array.from(
        new Set(
          optionChainRows
            .map((r) => asObj(r))
            .map((r) => (typeof r.expiry === 'string' ? r.expiry : ''))
            .filter(Boolean),
        ),
      ).sort(),
    [optionChainRows],
  );

  useEffect(() => {
    if (selectedExpiry !== 'ALL' && !chainExpiries.includes(selectedExpiry)) setSelectedExpiry('ALL');
  }, [selectedExpiry, chainExpiries]);

  const atm = underlying === 'BANKNIFTY'
    ? asNum(atmSnapshot.banknifty_atm_strike)
    : asNum(atmSnapshot.nifty_atm_strike);

  const visibleRows = useMemo(() => {
    const sourceRows = selectedExpiry === 'ALL'
      ? optionChainRows
      : optionChainRows.filter((r) => asObj(r).expiry === selectedExpiry);
    if (!sourceRows.length) return [];
    const mapped = sourceRows
      .map((r) => asObj(r))
      .filter((r) => asNum(r.strike) != null)
      .sort((a, b) => (asNum(a.strike) ?? 0) - (asNum(b.strike) ?? 0));
    if (atm == null) return mapped.slice(0, 24);
    return mapped
      .map((r) => ({ r, d: Math.abs((asNum(r.strike) ?? 0) - atm) }))
      .sort((a, b) => a.d - b.d)
      .slice(0, 25)
      .map((x) => x.r)
      .sort((a, b) => (asNum(a.strike) ?? 0) - (asNum(b.strike) ?? 0));
  }, [optionChainRows, atm, selectedExpiry]);

  const collectorLive = String(collector.status || '').toLowerCase() === 'running';
  const calculatorLive = String(calculator.status || '').toLowerCase() === 'running';
  const collectorWarmingUp = Boolean(collector.warming_up);
  const atmWarning = typeof atmSnapshot.warning === 'string' ? atmSnapshot.warning : null;
  const staleWarnings = [
    collectorWarmingUp ? 'Collector warming up: ticks are live, first persisted 1-minute bar appears after minute close.' : null,
    health.collector_stale ? 'Collector heartbeat is stale.' : null,
    health.calculator_stale ? 'Calculator heartbeat is stale.' : null,
    health.snapshots_stale ? 'One or more snapshots are stale.' : null,
  ].filter(Boolean) as string[];

  const runAction = async (actionId: string, fn: () => Promise<unknown>) => {
    setActionBusy(actionId);
    try {
      await fn();
      await fetchAll();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Action failed');
    } finally {
      setActionBusy(null);
    }
  };

  return (
    <div className="animate-in continuous-page">
      <div className="card" style={{ marginBottom: 'var(--space-lg)' }}>
        <div className="card-header" style={{ marginBottom: 10 }}>
          <span className="card-title">Control Bar</span>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <span className={`badge ${collectorLive ? 'badge-success' : 'badge-neutral'}`}>
              Collector: {collectorLive ? 'LIVE' : 'STOPPED'}
            </span>
            <span className={`badge ${calculatorLive ? 'badge-success' : 'badge-neutral'}`}>
              Calculator: {calculatorLive ? 'LIVE' : 'STOPPED'}
            </span>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(140px, 1fr))', gap: 'var(--space-sm)' }}>
          <button
            className="btn btn-success btn-sm"
            disabled={collectorLive || actionBusy !== null}
            onClick={() => runAction('start-collector', startCollector)}
          >
            <Tooltip content="Starts live WebSocket collection. This enables incoming ticks and 1-minute bar persistence, increasing live write load.">
              <span>{actionBusy === 'start-collector' ? 'Starting...' : 'Start Collector'}</span>
            </Tooltip>
          </button>
          <button
            className="btn btn-danger btn-sm"
            disabled={!collectorLive || actionBusy !== null}
            onClick={() => runAction('stop-collector', stopCollector)}
          >
            <Tooltip content="Stops live data ingestion. No new ticks/bars will arrive until restarted.">
              <span>{actionBusy === 'stop-collector' ? 'Stopping...' : 'Stop Collector'}</span>
            </Tooltip>
          </button>
          <button
            className="btn btn-success btn-sm"
            disabled={calculatorLive || actionBusy !== null}
            onClick={() => runAction('start-calc', startCalculator)}
          >
            <Tooltip content="Starts snapshot calculations (PCR, ATM OI, VIX) and keeps live market-view lens fresh for pulse monitoring.">
              <span>{actionBusy === 'start-calc' ? 'Starting...' : 'Start Calc'}</span>
            </Tooltip>
          </button>
          <button
            className="btn btn-danger btn-sm"
            disabled={!calculatorLive || actionBusy !== null}
            onClick={() => runAction('stop-calc', stopCalculator)}
          >
            <Tooltip content="Stops snapshot calculations. Existing snapshots remain visible but freshness will degrade over time.">
              <span>{actionBusy === 'stop-calc' ? 'Stopping...' : 'Stop Calc'}</span>
            </Tooltip>
          </button>
        </div>
      </div>

      {error ? <div className="card" style={{ marginBottom: 'var(--space-lg)', color: 'var(--red)' }}>{error}</div> : null}
      {staleWarnings.length || atmWarning ? (
        <div className="card" style={{ marginBottom: 'var(--space-lg)', color: '#92400e' }}>
          {[...staleWarnings, atmWarning].filter(Boolean).map((msg, idx) => (
            <div key={`mp-warning-${idx}`}>{msg}</div>
          ))}
        </div>
      ) : null}

      <div className="grid grid-4" style={{ marginBottom: 'var(--space-lg)' }}>
        <div className="card"><div className="stat-label">NIFTY Spot</div><div className="stat-value neutral">{marketView.market_view.NIFTY.spot?.price != null ? marketView.market_view.NIFTY.spot.price.toFixed(2) : '--'}</div></div>
        <div className="card"><div className="stat-label">NIFTY Basis</div><div className="stat-value neutral">{basisFromSpotAndFuture(marketView.market_view.NIFTY.spot?.price ?? null, marketView.market_view.NIFTY.futures[0]?.price ?? null) != null ? `${(basisFromSpotAndFuture(marketView.market_view.NIFTY.spot?.price ?? null, marketView.market_view.NIFTY.futures[0]?.price ?? null) as number).toFixed(2)}` : '--'}</div></div>
        <div className="card"><div className="stat-label">BANKNIFTY Spot</div><div className="stat-value neutral">{marketView.market_view.BANKNIFTY.spot?.price != null ? marketView.market_view.BANKNIFTY.spot.price.toFixed(2) : '--'}</div></div>
        <div className="card"><div className="stat-label">BANKNIFTY Basis</div><div className="stat-value neutral">{basisFromSpotAndFuture(marketView.market_view.BANKNIFTY.spot?.price ?? null, marketView.market_view.BANKNIFTY.futures[0]?.price ?? null) != null ? `${(basisFromSpotAndFuture(marketView.market_view.BANKNIFTY.spot?.price ?? null, marketView.market_view.BANKNIFTY.futures[0]?.price ?? null) as number).toFixed(2)}` : '--'}</div></div>
      </div>

      <div className="card" style={{ marginBottom: 'var(--space-lg)' }}>
        <div className="card-header">
          <span className="card-title">Market View</span>
          <div style={{ display: 'grid', gap: 4 }}>
            <TooltipLabel
              label="Underlying Lens"
              content="Switches universe focus for market-view lens and option chain. This does not change collector subscriptions."
            />
            <select style={{ width: 180 }} value={underlying} onChange={(e) => setUnderlying(e.target.value as 'NIFTY' | 'BANKNIFTY')}>
              <option value="NIFTY">NIFTY 50</option>
              <option value="BANKNIFTY">BANKNIFTY</option>
            </select>
          </div>
        </div>
        {(['NIFTY', 'BANKNIFTY'] as const).map((name) => {
          const side = marketView.market_view[name];
          const spot = side.spot?.price ?? null;
          const futures = side.futures || [];
          return (
            <div key={`mp-view-${name}`} style={{ marginBottom: 12 }}>
              <div className="stat-label" style={{ marginBottom: 4 }}>{name}</div>
              <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.max(2, futures.length + 1)}, minmax(0, 1fr))`, gap: 8 }}>
                <div style={{ background: 'var(--bg-subtle)', borderRadius: 6, padding: '6px 10px' }}>
                  <div className="stat-label">Spot</div>
                  <div className="stat-value neutral" style={{ fontSize: '1rem' }}>{spot != null ? spot.toFixed(2) : '--'}</div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{side.spot?.tradingsymbol || '--'}</div>
                </div>
                {futures.map((future, idx) => {
                  const basis = basisFromSpotAndFuture(spot, future.price);
                  return (
                    <div key={`mp-view-fut-${name}-${idx}`} style={{ background: 'var(--bg-subtle)', borderRadius: 6, padding: '6px 10px' }}>
                      <div className="stat-label">{idx === 0 ? 'Current Fut' : 'Next Fut'}</div>
                      <div className="stat-value neutral" style={{ fontSize: '1rem' }}>{future.price != null ? future.price.toFixed(2) : '--'}</div>
                      <div style={{ fontSize: '0.72rem', color: basis == null ? 'var(--text-muted)' : basis >= 0 ? 'var(--green)' : 'var(--red)' }}>
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

      <div className="grid grid-4" style={{ marginBottom: 'var(--space-lg)' }}>
        <div className="card"><div className="stat-label">VIX</div><div className="stat-value neutral">{(asNum(vixSnapshot.vix) ?? 0).toFixed(2)}</div></div>
        <div className="card"><div className="stat-label">NIFTY PCR</div><div className="stat-value neutral">{asNum(pcrSnapshot.nifty_pcr) != null ? (asNum(pcrSnapshot.nifty_pcr) as number).toFixed(4) : '--'}</div></div>
        <div className="card"><div className="stat-label">BANKNIFTY PCR</div><div className="stat-value neutral">{asNum(pcrSnapshot.banknifty_pcr) != null ? (asNum(pcrSnapshot.banknifty_pcr) as number).toFixed(4) : '--'}</div></div>
        <div className="card"><div className="stat-label">NIFTY ATM Strike</div><div className="stat-value neutral">{asNum(atmSnapshot.nifty_atm_strike) ?? '--'}</div></div>
        <div className="card"><div className="stat-label">BANKNIFTY ATM Strike</div><div className="stat-value neutral">{asNum(atmSnapshot.banknifty_atm_strike) ?? '--'}</div></div>
      </div>

      <div className="card" style={{ marginBottom: 'var(--space-lg)' }}>
        <div className="card-header">
          <span className="card-title">Runtime Status</span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-md)', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
          <div>Collector PID: {String(collector.pid ?? '--')}</div>
          <div>Calculator PID: {String(calculator.pid ?? '--')}</div>
          <div>Bars written: {String(collectorFile.bars_written ?? '--')}</div>
          <div>Ticks seen: {String(collector.ticks_seen ?? '--')}</div>
          <div>Tokens subscribed: {String(collectorFile.tokens_subscribed ?? '--')}</div>
          <div>Last tick at: {String(collectorFile.last_tick_at ?? '--')}</div>
          <div>Last bar at: {String(collectorFile.last_bar_at ?? '--')}</div>
          <div>Collector recent: {String(health.status_recent ?? '--')}</div>
          <div>Tick recent: {String(health.tick_recent ?? '--')}</div>
          <div>Bar recent: {String(health.bar_recent ?? '--')}</div>
          <div>Calculator last cycle: {String(calculator.last_cycle_at ?? '--')}</div>
          <div>Snapshots stale: {String(health.snapshots_stale ?? '--')}</div>
          <div>ATM OI fresh: {String(!asObj(snapshotHealth.atm_oi).stale || false)}</div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Option Chain ({underlying})</span>
          <div style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}>
            <div style={{ display: 'grid', gap: 4 }}>
              <TooltipLabel
                label="Expiry Filter"
                content="Filters option-chain rows by expiry. Narrowing expiry improves readability and can reveal expiry-specific OI structure."
              />
              <select value={selectedExpiry} onChange={(e) => setSelectedExpiry(e.target.value)} style={{ width: 160 }}>
                <option value="ALL">All Expiries</option>
                {chainExpiries.map((x) => (
                  <option key={x} value={x}>{x}</option>
                ))}
              </select>
            </div>
            <span className="badge badge-info">{visibleRows.length} strikes</span>
          </div>
        </div>
        <div className="table-wrapper" style={{ maxHeight: 420, overflow: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th>Strike</th>
                <th>CE LTP</th>
                <th>CE OI</th>
                <th>PE LTP</th>
                <th>PE OI</th>
                <th>Strike PCR</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row, idx) => {
                const strike = asNum(row.strike);
                const highlight = atm != null && strike != null && Math.abs(strike - atm) < 0.001;
                return (
                  <tr key={`${strike ?? idx}`} style={highlight ? { background: 'rgba(37,99,235,0.08)' } : undefined}>
                    <td>{strike ?? '--'}</td>
                    <td>{(asNum(row.ce_ltp) ?? 0).toFixed(2)}</td>
                    <td>{Math.round(asNum(row.ce_oi) ?? 0).toLocaleString()}</td>
                    <td>{(asNum(row.pe_ltp) ?? 0).toFixed(2)}</td>
                    <td>{Math.round(asNum(row.pe_oi) ?? 0).toLocaleString()}</td>
                    <td>{asNum(row.strike_pcr) != null ? (asNum(row.strike_pcr) as number).toFixed(4) : '--'}</td>
                  </tr>
                );
              })}
              {!visibleRows.length && (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
                    Option chain data not available.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
