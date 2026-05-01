interface PageMetaBarProps {
  items: string[];
  rightText?: string;
}

export default function PageMetaBar({ items, rightText }: PageMetaBarProps) {
  return (
    <div className="page-meta-bar" aria-label="Page context">
      <div className="page-meta-list">
        {items.map((item) => (
          <span key={item} className="page-meta-chip">
            {item}
          </span>
        ))}
      </div>
      {rightText ? <span className="page-meta-right">{rightText}</span> : null}
    </div>
  );
}
