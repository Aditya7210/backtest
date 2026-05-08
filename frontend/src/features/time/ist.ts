const IST_TIME_ZONE = 'Asia/Kolkata';
const IST_OFFSET_MINUTES = 330;

const IST_DATE_TIME_FORMATTER = new Intl.DateTimeFormat('en-IN', {
  timeZone: IST_TIME_ZONE,
  day: '2-digit',
  month: 'short',
  year: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
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

function parseEpochSeconds(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    const abs = Math.abs(value);
    return Math.floor(abs > 1_000_000_000_000 ? value / 1000 : value);
  }
  if (typeof value !== 'string') return null;
  const raw = value.trim();
  if (!raw) return null;
  if (!/^[+-]?\d+(\.\d+)?$/.test(raw)) return null;
  const numeric = Number(raw);
  if (!Number.isFinite(numeric)) return null;
  const abs = Math.abs(numeric);
  return Math.floor(abs > 1_000_000_000_000 ? numeric / 1000 : numeric);
}

function parseNaiveToUnix(raw: string): number | null {
  const input = raw.trim();
  if (!input) return null;
  const normalized = input.replace('T', ' ');
  const match = normalized.match(
    /^(\d{4})-(\d{2})-(\d{2})(?:\s+(\d{2})(?::(\d{2})(?::(\d{2}))?)?)?$/,
  );
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4] ?? '0');
  const minute = Number(match[5] ?? '0');
  const second = Number(match[6] ?? '0');
  if (!Number.isFinite(year) || !Number.isFinite(month) || !Number.isFinite(day)) return null;
  if (month < 1 || month > 12) return null;
  if (day < 1 || day > 31) return null;
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59 || second < 0 || second > 59) return null;
  const utcMillis = Date.UTC(year, month - 1, day, hour, minute, second) - (IST_OFFSET_MINUTES * 60 * 1000);
  if (!Number.isFinite(utcMillis)) return null;
  return Math.floor(utcMillis / 1000);
}

function parseTimestampToUnix(value: unknown, options: { naiveAsIst: boolean }): number | null {
  const { naiveAsIst } = options;
  const epoch = parseEpochSeconds(value);
  if (epoch != null) return epoch;
  if (typeof value !== 'string') return null;
  const raw = value.trim();
  if (!raw) return null;

  const hasExplicitZone = /([zZ]|[+-]\d{2}:\d{2})$/.test(raw);
  if (hasExplicitZone) {
    const millis = Date.parse(raw);
    return Number.isFinite(millis) ? Math.floor(millis / 1000) : null;
  }

  if (naiveAsIst) {
    const parsedNaive = parseNaiveToUnix(raw);
    if (parsedNaive != null) return parsedNaive;
  }

  const millis = Date.parse(`${raw}Z`);
  return Number.isFinite(millis) ? Math.floor(millis / 1000) : null;
}

export function parseTradeTimestampToUnix(value: unknown): number | null {
  return parseTimestampToUnix(value, { naiveAsIst: true });
}

export function formatTradeTimestampIst(value: unknown): string {
  const unix = parseTradeTimestampToUnix(value);
  if (unix == null) {
    const raw = typeof value === 'string' ? value.trim() : '';
    return raw || '--';
  }
  return formatUnixIst(unix, 'datetime');
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
