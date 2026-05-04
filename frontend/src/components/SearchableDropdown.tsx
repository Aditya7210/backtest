import { useEffect, useMemo, useRef, useState } from 'react';
import TooltipLabel from './TooltipLabel';

export interface SearchableOption {
  id: string;
  label: string;
  searchText?: string;
}

interface Props {
  label: string;
  value: string;
  options: SearchableOption[];
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  tooltipContent?: string;
}

export default function SearchableDropdown({
  label,
  value,
  options,
  onChange,
  placeholder = 'Search...',
  disabled = false,
  tooltipContent,
}: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const rootRef = useRef<HTMLDivElement | null>(null);

  const selected = useMemo(
    () => options.find((opt) => opt.id === value) ?? null,
    [options, value],
  );

  useEffect(() => {
    if (!open) return;
    const onDocClick = (evt: MouseEvent) => {
      if (!rootRef.current) return;
      const target = evt.target as Node;
      if (!rootRef.current.contains(target)) setOpen(false);
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter((opt) => {
      const hay = `${opt.label} ${opt.searchText || ''}`.toLowerCase();
      return hay.includes(q);
    });
  }, [options, query]);

  return (
    <div ref={rootRef} style={{ position: 'relative' }}>
      {tooltipContent ? (
        <TooltipLabel label={label} content={tooltipContent} />
      ) : (
        <label className="stat-label">{label}</label>
      )}
      <button
        type="button"
        className="input dropdown-trigger"
        onClick={() => !disabled && setOpen((prev) => !prev)}
        disabled={disabled}
        style={{ textAlign: 'left', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
      >
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {selected?.label || 'Select...'}
        </span>
        <span style={{ color: 'var(--text-muted)' }}>{open ? '▴' : '▾'}</span>
      </button>

      {open ? (
        <div
          style={{
            position: 'absolute',
            zIndex: 30,
            left: 0,
            right: 0,
            marginTop: 6,
            background: '#fff',
            border: '1px solid var(--border-subtle)',
            borderRadius: 8,
            boxShadow: '0 8px 24px rgba(15, 23, 42, 0.08)',
            padding: 8,
          }}
        >
          <input
            className="input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={placeholder}
            autoFocus
          />
          <div style={{ maxHeight: 260, overflowY: 'auto', marginTop: 8, display: 'grid', gap: 4 }}>
            <button
              type="button"
              className="btn btn-dropdown btn-sm"
              onClick={() => {
                onChange('');
                setOpen(false);
              }}
              style={{ justifyContent: 'flex-start' }}
            >
              Clear
            </button>
            {filtered.length ? (
              filtered.map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  className="btn btn-dropdown btn-sm"
                  onClick={() => {
                    onChange(opt.id);
                    setOpen(false);
                    setQuery('');
                  }}
                  style={{
                    justifyContent: 'flex-start',
                    background: opt.id === value ? 'var(--accent-soft)' : undefined,
                  }}
                >
                  {opt.label}
                </button>
              ))
            ) : (
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', padding: '6px 2px' }}>No matches</div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
