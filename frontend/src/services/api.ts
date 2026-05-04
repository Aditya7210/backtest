/* API service — all backend HTTP calls */

const BASE = '/api';
const DATE_ONLY_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

function normalizeDateOnlyInput(value: unknown, field: string): string {
  const raw = typeof value === 'string' ? value.trim() : '';
  if (!DATE_ONLY_PATTERN.test(raw)) {
    throw new Error(`Invalid ${field}. Expected YYYY-MM-DD.`);
  }
  return raw;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    let detail = `${res.status} ${res.statusText}`;
    if (text) {
      try {
        const parsed = JSON.parse(text) as { detail?: string };
        detail = parsed.detail || detail;
      } catch {
        detail = text.slice(0, 500);
      }
    }
    throw new Error(`[${path}] ${detail}`);
  }
  const bodyText = await res.text();
  if (!bodyText) return {} as T;
  try {
    return JSON.parse(bodyText) as T;
  } catch {
    throw new Error(`[${path}] Invalid JSON response`);
  }
}

/* Market Data */
export const getMarketBars = (token: number, tf = '1min', date?: string) =>
  request<{ bars: unknown[] }>(`/market/bars/${token}?timeframe=${tf}${date ? `&trading_date=${date}` : ''}`);

export const getLatestMarketTick = (token: number) =>
  request<{ instrument_token: number; tick: Record<string, unknown> | null }>(`/market/tick/${token}`);

export const getSnapshot = (type: string) =>
  request<Record<string, unknown>>(`/market/snapshot/${type}`);

export const getAllSnapshots = () =>
  request<Record<string, unknown>>('/market/snapshots/all');

export const getLiveInstruments = (params?: {
  q?: string;
  instrument_type?: string;
  universe?: string;
  underlying?: string;
  expiry?: string;
  timeframe?: string;
  trading_date?: string;
  data_source?: string;
  active_only?: boolean;
  stale_threshold_seconds?: number;
  limit?: number;
}) => {
  const qs = new URLSearchParams();
  if (params?.q) qs.set('q', params.q);
  if (params?.instrument_type) qs.set('instrument_type', params.instrument_type);
  if (params?.universe) qs.set('universe', params.universe);
  if (params?.underlying) qs.set('underlying', params.underlying);
  if (params?.expiry) qs.set('expiry', params.expiry);
  if (params?.timeframe) qs.set('timeframe', params.timeframe);
  if (params?.trading_date) qs.set('trading_date', params.trading_date);
  if (params?.data_source) qs.set('data_source', params.data_source);
  if (typeof params?.active_only === 'boolean') qs.set('active_only', String(params.active_only));
  if (params?.stale_threshold_seconds != null) qs.set('stale_threshold_seconds', String(params.stale_threshold_seconds));
  if (params?.limit != null) qs.set('limit', String(params.limit));
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  return request<Record<string, unknown>>(`/live/instruments${suffix}`);
};

export const getLiveUniverseHealth = (params?: {
  trading_date?: string;
  timeframe?: string;
  stale_threshold_seconds?: number;
}) => {
  const qs = new URLSearchParams();
  if (params?.trading_date) qs.set('trading_date', params.trading_date);
  if (params?.timeframe) qs.set('timeframe', params.timeframe);
  if (params?.stale_threshold_seconds != null) qs.set('stale_threshold_seconds', String(params.stale_threshold_seconds));
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  return request<Record<string, unknown>>(`/live/universe-health${suffix}`);
};

export const getMarketView = () =>
  request<Record<string, unknown>>('/live/market-view');

/* Historical Data */
export const getCatalog = () =>
  request<{ catalog: unknown[] }>('/historical/catalog');

export const getHistoricalBars = (token: number, tf: string, from: string, to: string) =>
  request<{ bars: unknown[]; total: number }>(`/historical/bars/${token}?timeframe=${tf}&date_from=${from}&date_to=${to}`);

export const searchInstruments = (query: string, limit = 20) =>
  request<{ items: unknown[]; source: string; warning?: string | null }>(
    `/instruments/search?q=${encodeURIComponent(query)}&limit=${limit}`,
  );

export const searchMapperInstruments = (query: string, limit = 20) =>
  request<{ items: unknown[]; source: string; warning?: string | null }>(
    `/instruments/mapper/search?q=${encodeURIComponent(query)}&limit=${limit}`,
  );

export const updateMapperInstruments = () =>
  request<{ status: string; rows_latest: number; rows_archive: number }>('/instruments/mapper/update', {
    method: 'POST',
  });

export const startHistoricalIngest = (body: unknown) =>
  request<{ job_id: string; status: string }>('/historical/ingest', {
    method: 'POST',
    body: (() => {
      const payload = (body && typeof body === 'object') ? { ...(body as Record<string, unknown>) } : {};
      if ('from_date' in payload) {
        payload.from_date = normalizeDateOnlyInput(payload.from_date, 'from_date');
      }
      if ('to_date' in payload) {
        payload.to_date = normalizeDateOnlyInput(payload.to_date, 'to_date');
      }
      return JSON.stringify(payload);
    })(),
  });

export const getHistoricalIngestJob = (jobId: string) =>
  request<Record<string, unknown>>(`/historical/ingest/${jobId}`);

/* Indicators */
export const getIndicators = () =>
  request<{ indicators: unknown[] }>('/indicators');

export const computeIndicators = (body: unknown) =>
  request<{ series: unknown[]; warnings?: string[] }>('/indicators/compute', {
    method: 'POST',
    body: JSON.stringify(body),
  });

/* Backtests */
export const runBacktest = (body: unknown) =>
  request<{ task_id: string; status: string }>('/backtests/run', { method: 'POST', body: JSON.stringify(body) });

export const getBacktests = () =>
  request<{ results: unknown[] }>('/backtests');

export const getBacktest = (id: string) =>
  request<unknown>(`/backtests/${id}`);

/* Strategies */
export const getStrategies = () =>
  request<{ strategies: unknown[] }>('/strategies');

export const getStrategySource = (name: string) =>
  request<{ name: string; source: string }>(`/strategies/${name}`);

export const getStrategyClasses = (name: string) =>
  request<{ name: string; classes: string[] }>(`/strategies/${name}/classes`);

export const getStrategySourceById = (strategyId: string, name?: string) =>
  request<{ name: string; strategy_id?: string; source: string }>(
    `/strategies/source?strategy_id=${encodeURIComponent(strategyId)}${name ? `&name=${encodeURIComponent(name)}` : ''}`,
  );

export const getStrategyClassesById = (strategyId: string, name?: string) =>
  request<{ name: string; strategy_id?: string; classes: string[] }>(
    `/strategies/classes?strategy_id=${encodeURIComponent(strategyId)}${name ? `&name=${encodeURIComponent(name)}` : ''}`,
  );

export const saveStrategy = (
  name: string,
  source: string,
  options?: { strategy_id?: string | null; versioning_enabled?: boolean },
) =>
  request<{ status: string; name: string; strategy_id?: string }>(
    '/strategies',
    {
      method: 'POST',
      body: JSON.stringify({
        name,
        source,
        strategy_id: options?.strategy_id ?? null,
        versioning_enabled: Boolean(options?.versioning_enabled),
      }),
    },
  );

/* Collector */
export const getCollectorStatus = () =>
  request<unknown>('/collector/status');

export const startCollector = () =>
  request<unknown>('/collector/start', { method: 'POST' });

export const stopCollector = () =>
  request<unknown>('/collector/stop', { method: 'POST' });

export const startCalculator = () =>
  request<unknown>('/calculator/start', { method: 'POST' });

export const stopCalculator = () =>
  request<unknown>('/calculator/stop', { method: 'POST' });

/* Auth */
export const getAuthStatus = () =>
  request<{
    api_key_set: boolean;
    api_secret_set: boolean;
    access_token_set: boolean;
    token_date: string;
    token_is_current_day: boolean;
    auth_ready: boolean;
  }>('/auth/status');

export const getZerodhaLoginUrl = () =>
  request<{ login_url: string }>('/auth/login-url');

export const generateZerodhaAccessToken = (requestToken: string) =>
  request<{ status: string; token_date: string }>('/auth/generate-token', {
    method: 'POST',
    body: JSON.stringify({ request_token: requestToken }),
  });

export const updateAccessTokenManual = (accessToken: string, tokenDate?: string) =>
  request<{ status: string; token_date: string }>('/auth/token', {
    method: 'POST',
    body: JSON.stringify({ access_token: accessToken, token_date: tokenDate ?? '' }),
  });
