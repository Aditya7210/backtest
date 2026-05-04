import Tooltip from './Tooltip';

interface TooltipLabelProps {
  label: string;
  content: string;
  htmlFor?: string;
  className?: string;
}

export default function TooltipLabel({ label, content, htmlFor, className }: TooltipLabelProps) {
  return (
    <label className={`stat-label tooltip-field-label${className ? ` ${className}` : ''}`} htmlFor={htmlFor}>
      <span>{label}</span>
      <Tooltip content={content}>
        <span className="tooltip-help-icon" aria-label={`${label} help`} role="img">?</span>
      </Tooltip>
    </label>
  );
}
