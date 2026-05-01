import { useEffect, useMemo, useState } from 'react';
import { getCollectorStatus, getSnapshot, startCalculator, startCollector, stopCalculator, stopCollector } from '../services/api';
import PageMetaBar from '../components/PageMetaBar';

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
  const [adSnapshot, setAdSnapshot] = useState<Snapshot>({});
  const [pcrSnapshot, setPcrSnapshot] = useState<Snapshot>({});
  const [vixSnapshot, setVixSnapshot] = useState<Snapshot>({});
  const [atmSnapshot, setAtmSnapshot] = useState<Snapshot>({});
  const [underlying, setUnderlying] = useState<'NIFTY' | 'BANKNIFTY'>('NIFTY');
  const [error, setError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    let timer: number | null = null;

    const fetchAll = async () => {
      try {
        const [status, ad, pcr, vix, atm] = await Promise.all([
          getCollectorStatus(),
          getSnapshot('ad'),
          getSnapshot('pcr'),
          getSnapshot('vix'),
          getSnapshot('atm_oi'),
        ]);
        if (!mounted) return;
        setCollectorStatus(asObj(status));
        setAdSnapshot(parseSnapshot(ad));
        setPcrSnapshot(parseSnapshot(pcr));
        setVixSnapshot(parseSnapshot(vix));
        setAtmSnapshot(parseSnapshot(atm));
        setError(null);
      } catch (e: unknown) {
        if (!mounted) return;
        setError(e instanceof Error ? e.message : 'Failed to refresh market pulse');
      }
    };

    fetchAll();
    timer = window.setInterval(fetchAll, 1000);
    return () => {
      mounted = false;
      if (timer != null) window.clearInterval(timer);
    };
  }, []);

  const collector = asObj(collectorStatus.collector);
  const calculator = asObj(collectorStatus.calculator);
  const collectorFile = asObj(collectorStatus.collector_file_status);
  const health = asObj(collectorStatus.collector_status_health);

  const adData = useMemo(() => {
    const universes = asObj(adSnapshot.universes);
    const selected =
      (underlying === 'BANKNIFTY' ? asObj(universes['NIFTY BANK']) : asObj(universes['NIFTY 50']));
    return Object.keys(selected).length ? selected : adSnapshot;
  }, [adSnapshot, underlying]);

  const optionChainRows = useMemo(() => {
    const chainRoot = asObj(pcrSnapshot.option_chain);
    const rows = chainRoot[underlying];
    return Array.isArray(rows) ? rows : [];
  }, [pcrSnapshot, underlying]);

  const atm = underlying === 'BANKNIFTY'
    ? asNum(atmSnapshot.banknifty_atm_strike)
    : asNum(atmSnapshot.nifty_atm_strike);

  const visibleRows = useMemo(() => {
    if (!optionChainRows.length) return [];
    const mapped = optionChainRows
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
  }, [optionChainRows, atm]);

  const collectorLive = String(collector.status || '').toLowerCase() === 'running';
  const calculatorLive = String(calculator.status || '').toLowerCase() === 'running';

  const runAction = async (actionId: string, fn: () => Promise<unknown>) => {
    setActionBusy(actionId);
    try {
      await fn();
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Action failed');
    } finally {
      setActionBusy(null);
    }
  };

  return (
    <div className="animate-in">
      <div className="page-header">
        <h1 className="page-title">Market Pulse</h1>
        <p className="page-subtitle">Real-time collector, calculator and snapshot monitoring</p>
        <PageMetaBar
          items={['Collector Controls', 'Calculator Controls', 'Snapshot Monitoring']}
          rightText="Auto refresh 1s"
        />
      </div>

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
            {actionBusy === 'start-collector' ? 'Starting...' : 'Start Collector'}
          </button>
          <button
            className="btn btn-danger btn-sm"
            disabled={!collectorLive || actionBusy !== null}
            onClick={() => runAction('stop-collector', stopCollector)}
          >
            {actionBusy === 'stop-collector' ? 'Stopping...' : 'Stop Collector'}
          </button>
          <button
            className="btn btn-success btn-sm"
            disabled={calculatorLive || actionBusy !== null}
            onClick={() => runAction('start-calc', startCalculator)}
          >
            {actionBusy === 'start-calc' ? 'Starting...' : 'Start Calc'}
          </button>
          <button
            className="btn btn-danger btn-sm"
            disabled={!calculatorLive || actionBusy !== null}
            onClick={() => runAction('stop-calc', stopCalculator)}
          >
            {actionBusy === 'stop-calc' ? 'Stopping...' : 'Stop Calc'}
          </button>
        </div>
      </div>

      {error ? <div className="card" style={{ marginBottom: 'var(--space-lg)', color: 'var(--red)' }}>{error}</div> : null}

      <div className="grid grid-4" style={{ marginBottom: 'var(--space-lg)' }}>
        <div className="card"><div className="stat-label">Advances</div><div className="stat-value neutral">{asNum(adData.advances) ?? 0}</div></div>
        <div className="card"><div className="stat-label">Declines</div><div className="stat-value neutral">{asNum(adData.declines) ?? 0}</div></div>
        <div className="card"><div className="stat-label">A/D Ratio</div><div className="stat-value neutral">{(asNum(adData.ad_ratio) ?? 0).toFixed(4)}</div></div>
        <div className="card"><div className="stat-label">VIX</div><div className="stat-value neutral">{(asNum(vixSnapshot.vix) ?? 0).toFixed(2)}</div></div>
      </div>

      <div className="grid grid-4" style={{ marginBottom: 'var(--space-lg)' }}>
        <div className="card"><div className="stat-label">NIFTY PCR</div><div className="stat-value neutral">{(asNum(pcrSnapshot.nifty_pcr) ?? 0).toFixed(4)}</div></div>
        <div className="card"><div className="stat-label">BANKNIFTY PCR</div><div className="stat-value neutral">{(asNum(pcrSnapshot.banknifty_pcr) ?? 0).toFixed(4)}</div></div>
        <div className="card"><div className="stat-label">NIFTY ATM Strike</div><div className="stat-value neutral">{asNum(atmSnapshot.nifty_atm_strike) ?? '--'}</div></div>
        <div className="card"><div className="stat-label">BANKNIFTY ATM Strike</div><div className="stat-value neutral">{asNum(atmSnapshot.banknifty_atm_strike) ?? '--'}</div></div>
      </div>

      <div className="card" style={{ marginBottom: 'var(--space-lg)' }}>
        <div className="card-header">
          <span className="card-title">Runtime Status</span>
          <select style={{ width: 180 }} value={underlying} onChange={(e) => setUnderlying(e.target.value as 'NIFTY' | 'BANKNIFTY')}>
            <option value="NIFTY">NIFTY 50</option>
            <option value="BANKNIFTY">BANKNIFTY</option>
          </select>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-md)', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
          <div>Collector PID: {String(collector.pid ?? '--')}</div>
          <div>Calculator PID: {String(calculator.pid ?? '--')}</div>
          <div>Bars written: {String(collectorFile.bars_written ?? '--')}</div>
          <div>Tokens subscribed: {String(collectorFile.tokens_subscribed ?? '--')}</div>
          <div>Last tick at: {String(collectorFile.last_tick_at ?? '--')}</div>
          <div>Status freshness ok: {String(health.status_recent ?? '--')}</div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Option Chain ({underlying})</span>
          <span className="badge badge-info">{visibleRows.length} strikes</span>
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
                    <td>{(asNum(row.strike_pcr) ?? 0).toFixed(4)}</td>
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
