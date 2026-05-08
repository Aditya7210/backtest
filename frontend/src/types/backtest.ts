/* Backtest types */
export interface BacktestRequest {
  strategy_name: string;
  strategy_id?: string | null;
  strategy_class_name?: string | null;
  instrument_token: number;
  timeframe: string;
  date_from: string;
  date_to: string;
  initial_capital: number;
  commission: number;
  slippage?: number;
  lot_size?: number;
  position_size?: number;
  max_positions?: number;
  execution_mode?: string;
  max_retries?: number;
  task_timeout_seconds?: number;
  enforce_market_hours: boolean;
}

export interface BacktestResult {
  task_id: string;
  strategy_name: string;
  symbol: string;
  data_selection?: {
    instrument_token: number;
    tradingsymbol?: string;
    timeframe: string;
    date_from: string;
    date_to: string;
  } | null;
  config?: Record<string, unknown>;
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';
  started_at: string | null;
  completed_at: string | null;
  final_value: number | null;
  metrics: Record<string, unknown>;
  trades: Trade[];
  order_events?: OrderEvent[];
  integrity?: Record<string, unknown>;
  result_schema_version?: number;
  error_message: string | null;
  log_lines?: string[];
}

export interface Trade {
  trade_id?: string;
  instrument_token?: number | null;
  symbol?: string;
  entry_date: string;
  exit_date: string;
  entry_time_ist?: string | null;
  exit_time_ist?: string | null;
  entry_time_unix?: number | null;
  exit_time_unix?: number | null;
  direction: string;
  entry_action?: string;
  exit_action?: string;
  entry_price: number;
  exit_price: number;
  pnl: number;
  net_pnl?: number;
  gross_pnl?: number;
  commission?: number;
  size: number;
  quantity?: number;
  bars_held?: number;
  status?: string;
  position_before_entry?: number | null;
  position_after_entry?: number | null;
  position_before_exit?: number | null;
  position_after_exit?: number | null;
}

export interface OrderEvent {
  event_id?: string;
  time: string;
  event_time_ist?: string | null;
  event_time_unix?: number | null;
  action: string;
  status: string;
  requested_size?: number | null;
  executed_size?: number | null;
  price?: number | null;
  reason?: string | null;
  position_before?: number | null;
  position_after?: number | null;
  cash_before?: number | null;
  cash_after?: number | null;
}

export interface Strategy {
  name: string;
  filename: string;
  relative_path?: string;
  size_bytes: number;
  immutable?: boolean;
}

export interface InstrumentSearchResult {
  instrument_token: number;
  tradingsymbol: string;
  name?: string;
  segment?: string;
  exchange?: string;
  instrument_type?: string;
  expiry?: string;
  strike?: string;
  available_from?: string;
  available_to?: string;
}

export interface HistoricalIngestJob {
  job_id: string;
  status: 'PENDING' | 'RUNNING' | 'CANCEL_REQUESTED' | 'CANCELLED' | 'COMPLETED' | 'FAILED' | 'NO_DATA';
  phase?: 'PENDING' | 'FETCHING' | 'NORMALIZING' | 'SAVING' | 'COMMITTING' | 'CATALOG_REFRESH' | 'CLEANUP' | 'CANCEL_REQUESTED' | 'CANCELLED' | 'COMPLETED' | 'FAILED' | 'NO_DATA' | 'STALE' | string;
  request?: {
    instrument_token: number;
    tradingsymbol: string;
    from_date: string;
    to_date: string;
    interval: string;
    mode?: 'skip_existing' | 'overwrite' | 'append_only' | string;
  };
  rows?: number;
  rows_fetched?: number;
  saved_rows?: number;
  inserted?: number;
  modified?: number;
  skipped_existing_dates?: number;
  current_chunk?: number;
  total_chunks?: number;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  updated_at?: string | null;
  cancel_requested_at?: string | null;
  cleanup_started_at?: string | null;
  cleanup_completed_at?: string | null;
  estimated_finish_at?: string | null;
  ingest_job_id?: string | null;
  log_lines?: string[];
  performance?: {
    fetch_seconds?: number;
    normalize_seconds?: number;
    write_seconds?: number;
    commit_seconds?: number;
    catalog_refresh_seconds?: number;
    rows_per_second?: number;
    chunks_per_second?: number;
    mode?: string;
  };
}

export interface CatalogEntry {
  instrument_token: number;
  tradingsymbol: string;
  timeframes_available: {
    timeframe: string;
    date_from: string;
    date_to: string;
    total_bars: number;
    data_source?: 'historical' | 'live' | 'mixed' | string;
  }[];
}
