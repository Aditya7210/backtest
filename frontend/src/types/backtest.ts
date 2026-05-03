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
  error_message: string | null;
  log_lines?: string[];
}

export interface Trade {
  entry_date: string;
  exit_date: string;
  direction: string;
  entry_price: number;
  exit_price: number;
  pnl: number;
  size: number;
}

export interface Strategy {
  name: string;
  filename: string;
  relative_path?: string;
  size_bytes: number;
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
}

export interface HistoricalIngestJob {
  job_id: string;
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'NO_DATA';
  request?: {
    instrument_token: number;
    tradingsymbol: string;
    from_date: string;
    to_date: string;
    interval: string;
  };
  rows?: number;
  inserted?: number;
  current_chunk?: number;
  total_chunks?: number;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  updated_at?: string | null;
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
