/* API service — all backend HTTP calls */

const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

/* Market Data */
export const getMarketBars = (token: number, tf = '1min', date?: string) =>
  request<{ bars: unknown[] }>(`/market/bars/${token}?timeframe=${tf}${date ? `&trading_date=${date}` : ''}`);

export const getSnapshot = (type: string) =>
  request<Record<string, unknown>>(`/market/snapshot/${type}`);

export const getAllSnapshots = () =>
  request<Record<string, unknown>>('/market/snapshots/all');

/* Historical Data */
export const getCatalog = () =>
  request<{ catalog: unknown[] }>('/historical/catalog');

export const getHistoricalBars = (token: number, tf: string, from: string, to: string) =>
  request<{ bars: unknown[]; total: number }>(`/historical/bars/${token}?timeframe=${tf}&date_from=${from}&date_to=${to}`);

export const searchInstruments = (query: string, limit = 20) =>
  request<{ items: unknown[]; source: string; warning?: string | null }>(
    `/instruments/search?q=${encodeURIComponent(query)}&limit=${limit}`,
  );

export const startHistoricalIngest = (body: unknown) =>
  request<{ job_id: string; status: string }>('/historical/ingest', {
    method: 'POST',
    body: JSON.stringify(body),
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
