/* Market data types */
export interface OHLCVBar {
  time: number; // UNIX seconds for TradingView (E-09)
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  oi?: number | null;
}

export type LiveTimeframe =
  | '1min'
  | '3min'
  | '5min'
  | '10min'
  | '15min'
  | '20min'
  | '30min'
  | '45min'
  | '60min'
  | '1day';

export interface LiveTick {
  instrument_token: number;
  last_price: number;
  volume_traded?: number;
  oi?: number;
  time: number;
  timestamp?: string;
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

export interface LiveInstrumentItem {
  instrument_token: number;
  tradingsymbol: string;
  instrument_type: string;
  data_source: string;
  timeframe: string;
  trading_date: string;
  first_bar_at?: string | null;
  last_bar_at?: string | null;
  first_bar_time?: number | null;
  last_bar_time?: number | null;
  total_bars: number;
  last_close?: number | null;
  exchange?: string;
  segment?: string;
  underlying?: string;
  expiry?: string;
  strike?: number | null;
  option_type?: string;
  is_active: boolean;
  stale_seconds?: number | null;
}

export interface LiveUniverseHealth {
  nifty_spot_present: boolean;
  banknifty_spot_present: boolean;
  nifty_option_tokens: number;
  banknifty_option_tokens: number;
  nifty_ce_count: number;
  nifty_pe_count: number;
  banknifty_ce_count: number;
  banknifty_pe_count: number;
  nifty_futures_count: number;
  banknifty_futures_count: number;
  active_instruments: number;
  stale_instruments: number;
  total_instruments: number;
}

export interface MarketViewSpot {
  price: number | null;
  tradingsymbol: string;
  updated_at: string | null;
}

export interface MarketViewFuture {
  price: number | null;
  tradingsymbol: string;
  expiry: string | null;
  oi: number;
  updated_at: string | null;
}

export interface MarketViewSide {
  spot: MarketViewSpot | null;
  futures: MarketViewFuture[];
}

export interface MarketViewResponse {
  generated_at: string | null;
  market_view: Record<'NIFTY' | 'BANKNIFTY', MarketViewSide>;
}
