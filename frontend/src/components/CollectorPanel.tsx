import type { CollectorStatus } from '../types/market';
import { startCollector, stopCollector, startCalculator, stopCalculator } from '../services/api';

interface Props { status: CollectorStatus | null; }

export default function CollectorPanel({ status }: Props) {
  const cs = status?.collector;
  const calc = status?.calculator;

  return (
    <div className="card">
      <div className="card-header"><span className="card-title">System Services</span></div>
      <div style={{display:'flex',flexDirection:'column',gap:'var(--space-lg)'}}>
        <div>
          <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:'var(--space-sm)'}}>
            <div style={{display:'flex',alignItems:'center',gap:'8px'}}>
              <span className={`status-dot ${cs?.status==='running'?'running':cs?.last_error?'error':'stopped'}`}></span>
              <span style={{fontWeight:600,fontSize:'0.9rem'}}>Collector</span>
            </div>
            <div style={{display:'flex',gap:'var(--space-sm)'}}>
              <button className="btn btn-success btn-sm" onClick={()=>startCollector()} disabled={cs?.status==='running'}>Start</button>
              <button className="btn btn-danger btn-sm" onClick={()=>stopCollector()} disabled={cs?.status!=='running'}>Stop</button>
            </div>
          </div>
          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:'4px',fontSize:'0.8rem',color:'var(--text-muted)'}}>
            <span>Bars: <b style={{color:'var(--text-primary)'}}>{cs?.bars_written??0}</b></span>
            <span>Tokens: <b style={{color:'var(--text-primary)'}}>{cs?.tokens_subscribed??0}</b></span>
          </div>
        </div>
        <div style={{borderTop:'1px solid var(--border-subtle)',paddingTop:'var(--space-md)'}}>
          <div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}>
            <div style={{display:'flex',alignItems:'center',gap:'8px'}}>
              <span className={`status-dot ${calc?.status==='running'?'running':'stopped'}`}></span>
              <span style={{fontWeight:600,fontSize:'0.9rem'}}>Calculator</span>
            </div>
            <div style={{display:'flex',gap:'var(--space-sm)'}}>
              <button className="btn btn-success btn-sm" onClick={()=>startCalculator()} disabled={calc?.status==='running'}>Start</button>
              <button className="btn btn-danger btn-sm" onClick={()=>stopCalculator()} disabled={calc?.status!=='running'}>Stop</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
