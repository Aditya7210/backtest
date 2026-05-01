interface Props {
  id: string;
  label: string;
  value: string;
  change?: string;
  subtitle?: string;
  variant?: 'positive' | 'negative' | 'neutral';
}

export default function StatCard({ id, label, value, change, subtitle, variant = 'neutral' }: Props) {
  return (
    <div className="card" id={id}>
      <div className="stat-label">{label}</div>
      <div className={`stat-value ${variant}`}>{value}</div>
      {change && <div style={{fontSize:'0.8rem',marginTop:'2px',color: variant === 'positive' ? 'var(--green)' : variant === 'negative' ? 'var(--red)' : 'var(--text-muted)'}}>{change}</div>}
      {subtitle && <div style={{fontSize:'0.8rem',color:'var(--text-muted)',marginTop:'2px'}}>{subtitle}</div>}
    </div>
  );
}
