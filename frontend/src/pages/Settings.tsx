import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getAuthStatus, getCollectorStatus } from '../services/api';
import PageMetaBar from '../components/PageMetaBar';

function asObj(v: unknown): Record<string, unknown> {
  return v && typeof v === 'object' ? (v as Record<string, unknown>) : {};
}

export default function SettingsPage() {
  const [auth, setAuth] = useState<{ api_key_set: boolean; access_token_set: boolean; token_date: string } | null>(null);
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    const refresh = async () => {
      try {
        const [authStatus, collectorStatus] = await Promise.all([getAuthStatus(), getCollectorStatus()]);
        if (!mounted) return;
        setAuth(authStatus);
        setStatus(asObj(collectorStatus));
        setError(null);
      } catch (e: unknown) {
        if (!mounted) return;
        setError(e instanceof Error ? e.message : 'Failed to load settings status');
      }
    };
    refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, []);

  const collector = asObj(status?.collector);
  const calculator = asObj(status?.calculator);
  const collectorLive = String(collector.status || '').toLowerCase() === 'running';
  const calculatorLive = String(calculator.status || '').toLowerCase() === 'running';

  return (
    <div className="animate-in">
      <div className="page-header">
        <h1 className="page-title">Settings</h1>
        <p className="page-subtitle">System diagnostics, page connections, and runtime ownership boundaries</p>
        <PageMetaBar
          items={['Read-Only Diagnostics', 'Runtime Ownership', 'Connection Visibility']}
          rightText="No runtime controls on this page"
        />
      </div>

      {error ? (
        <div className="card" style={{ marginBottom: 'var(--space-lg)', borderColor: 'var(--red-dim)', color: 'var(--red)' }}>
          {error}
        </div>
      ) : null}

      <div className="grid grid-3" style={{ marginBottom: 'var(--space-lg)' }}>
        <div className="card">
          <div className="stat-label">Auth API Key</div>
          <div className={`stat-value ${auth?.api_key_set ? 'positive' : 'negative'}`}>{auth?.api_key_set ? 'SET' : 'MISSING'}</div>
        </div>
        <div className="card">
          <div className="stat-label">Auth Access Token</div>
          <div className={`stat-value ${auth?.access_token_set ? 'positive' : 'negative'}`}>{auth?.access_token_set ? 'SET' : 'MISSING'}</div>
        </div>
        <div className="card">
          <div className="stat-label">Runtime Health</div>
          <div className="stat-value neutral">{collectorLive || calculatorLive ? 'ACTIVE' : 'IDLE'}</div>
        </div>
      </div>

      <div className="grid grid-2">
        <div className="card">
          <div className="card-header"><span className="card-title">Service State (Read-Only)</span></div>
          <div style={{ display: 'grid', gap: 8, fontSize: '0.86rem', color: 'var(--text-secondary)' }}>
            <div>Collector: <b>{String(collector.status ?? 'unknown')}</b></div>
            <div>Collector PID: {String(collector.pid ?? '--')}</div>
            <div>Calculator: <b>{String(calculator.status ?? 'unknown')}</b></div>
            <div>Calculator PID: {String(calculator.pid ?? '--')}</div>
          </div>
        </div>

        <div className="card">
          <div className="card-header"><span className="card-title">Page Ownership</span></div>
          <div style={{ display: 'grid', gap: 10 }}>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.86rem' }}>
              Collector and calculator controls are intentionally centralized in the dedicated runtime page.
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <Link className="btn btn-primary btn-sm" to="/market-pulse">Open Market Pulse</Link>
              <Link className="btn btn-ghost btn-sm" to="/">Open Zerodha Auth</Link>
              <Link className="btn btn-ghost btn-sm" to="/backtest">Open Backtests</Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
