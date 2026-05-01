import { useState, useEffect } from 'react';
import { getStrategies, getStrategySource, saveStrategy } from '../services/api';
import type { Strategy } from '../types/backtest';
import PageMetaBar from '../components/PageMetaBar';

export default function StrategiesPage() {
  const [strategies, setStrats] = useState<Strategy[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [source, setSource] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => { getStrategies().then(d => setStrats(d.strategies as Strategy[])).catch(() => {}); }, []);

  const loadSource = async (name: string) => {
    setSelected(name);
    try { const d = await getStrategySource(name); setSource(d.source); } catch { setSource('// Failed to load'); }
  };

  const handleSave = async () => {
    if (!selected) return;
    setSaving(true);
    try { await saveStrategy(selected, source); } catch { /* ignore */ }
    finally { setSaving(false); }
  };

  return (
    <div className="animate-in">
      <div className="page-header">
        <h1 className="page-title">Strategies</h1>
        <p className="page-subtitle">Manage Backtrader strategy files</p>
        <PageMetaBar
          items={['Backtrader Source', 'Live Editor', 'Version-Safe Save']}
          rightText="Strategy workspace"
        />
      </div>
      <div className="grid grid-3">
        <div className="card">
          <div className="card-header"><span className="card-title">Files</span><span className="badge badge-neutral">{strategies.length}</span></div>
          {strategies.map(s => (
            <div key={s.name} className={`nav-link ${selected === s.name ? 'active' : ''}`} onClick={() => loadSource(s.name)}>
              <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14,2 14,8 20,8"/></svg>
              {s.name}.py
            </div>
          ))}
          {strategies.length === 0 && <p style={{color: 'var(--text-muted)', padding: 'var(--space-md)', fontSize: '0.85rem'}}>No strategies found in Strategies/Strategy_codes/</p>}
        </div>
        <div className="card" style={{gridColumn: 'span 2'}}>
          <div className="card-header">
            <span className="card-title">{selected ? `${selected}.py` : 'Select a strategy'}</span>
            {selected && <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>{saving ? 'Saving...' : 'Save'}</button>}
          </div>
          <textarea
            className="input"
            value={source}
            onChange={e => setSource(e.target.value)}
            style={{fontFamily: 'var(--font-mono)', fontSize: '0.8rem', minHeight: '500px', resize: 'vertical', lineHeight: '1.6'}}
            placeholder="Select a strategy file to view/edit..."
            readOnly={!selected}
          />
        </div>
      </div>
    </div>
  );
}
