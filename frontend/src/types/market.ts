/* Market data types */
export interface OHLCVBar {
  time: number; // UNIX seconds for TradingView (E-09)
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Snapshot {
  snapshot_type: string;
  generated_at: string;
  trading_date: string;
  data: Record<string, unknown>;
}

export interface VWAPSnapshot {
  generated_at: string;
  data: Record<string, Record<string, number>>;
}

export interface ADSnapshot {
  generated_at: string;
  advances: number;
  declines: number;
  unchanged: number;
  ad_ratio: number;
}

export interface PCRSnapshot {
  generated_at: string;
  nifty_pcr: number;
  banknifty_pcr: number;
  nifty_call_oi: number;
  nifty_put_oi: number;
  banknifty_call_oi: number;
  banknifty_put_oi: number;
}

export interface VIXSnapshot {
  generated_at: string;
  vix: number | null;
  vix_open: number | null;
}

export interface CollectorStatus {
  collector: {
    status: string;
    pid: number | null;
    trading_date?: string | null;
    started_at?: string | null;
    tokens_subscribed: number;
    bars_written: number;
    last_tick_at: string | null;
    last_error: string | null;
  };
  calculator: {
    status: string;
    pid: number | null;
    last_run_at?: string | null;
    last_error: string | null;
  };
}

export interface Instrument {
  instrument_token: number;
  tradingsymbol: string;
  exchange: string;
  segment: string;
  instrument_type: string;
}
