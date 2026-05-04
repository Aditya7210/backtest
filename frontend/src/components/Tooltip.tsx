import { type ReactNode, useEffect, useRef, useState } from 'react';

interface TooltipProps {
  content: ReactNode;
  children: ReactNode;
  delayMs?: number;
  disabled?: boolean;
  placement?: 'top' | 'bottom';
}

export default function Tooltip({
  content,
  children,
  delayMs = 2000,
  disabled = false,
  placement = 'top',
}: TooltipProps) {
  const [open, setOpen] = useState(false);
  const timerRef = useRef<number | null>(null);

  const clearTimer = () => {
    if (timerRef.current != null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  useEffect(() => () => clearTimer(), []);

  if (disabled) return <>{children}</>;

  return (
    <span
      className="tooltip-anchor"
      onMouseEnter={() => {
        clearTimer();
        timerRef.current = window.setTimeout(() => setOpen(true), delayMs);
      }}
      onMouseLeave={() => {
        clearTimer();
        setOpen(false);
      }}
      onFocus={() => {
        clearTimer();
        timerRef.current = window.setTimeout(() => setOpen(true), delayMs);
      }}
      onBlur={() => {
        clearTimer();
        setOpen(false);
      }}
      tabIndex={0}
    >
      {children}
      <span
        className={`tooltip-popover tooltip-${placement}${open ? ' open' : ''}`}
        role="tooltip"
      >
        {content}
      </span>
    </span>
  );
}
