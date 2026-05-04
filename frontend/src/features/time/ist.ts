const IST_TIME_ZONE = 'Asia/Kolkata';

const IST_DATE_TIME_FORMATTER = new Intl.DateTimeFormat('en-IN', {
  timeZone: IST_TIME_ZONE,
  day: '2-digit',
  month: 'short',
  year: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

function normalizeIsoToUtc(value: string): string {
  const raw = value.trim();
  if (!raw) return raw;
  if (/[zZ]$/.test(raw) || /[+-]\d{2}:\d{2}$/.test(raw)) return raw;
  return `${raw}Z`;
}

const IST_TIME_ONLY_FORMATTER = new Intl.DateTimeFormat('en-IN', {
  timeZone: IST_TIME_ZONE,
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

const IST_DATE_ONLY_FORMATTER = new Intl.DateTimeFormat('en-IN', {
  timeZone: IST_TIME_ZONE,
  day: '2-digit',
  month: 'short',
  year: '2-digit',
});

export function formatUnixIst(seconds: number, mode: 'time' | 'date' | 'datetime' = 'datetime'): string {
  if (!Number.isFinite(seconds)) return '--';
  const dt = new Date(Math.floor(seconds) * 1000);
  if (Number.isNaN(dt.getTime())) return '--';
  if (mode === 'time') return IST_TIME_ONLY_FORMATTER.format(dt);
  if (mode === 'date') return IST_DATE_ONLY_FORMATTER.format(dt);
  return IST_DATE_TIME_FORMATTER.format(dt);
}

export function formatIsoIst(value: string | null | undefined): string {
  if (!value) return '--';
  const dt = new Date(normalizeIsoToUtc(value));
  if (Number.isNaN(dt.getTime())) return value;
  return IST_DATE_TIME_FORMATTER.format(dt);
}

export function todayIstDate(): string {
  const now = new Date();
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: IST_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now);
  const year = parts.find((p) => p.type === 'year')?.value ?? '1970';
  const month = parts.find((p) => p.type === 'month')?.value ?? '01';
  const day = parts.find((p) => p.type === 'day')?.value ?? '01';
  return `${year}-${month}-${day}`;
}
