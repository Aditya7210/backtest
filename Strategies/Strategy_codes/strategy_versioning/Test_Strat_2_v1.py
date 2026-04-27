"""
Strategy: Trend + Pullback Momentum
===================================
A daily timeframe strategy that trades in the direction of the trend
and enters on pullbacks with momentum confirmation.

Indicators Used:
- EMA 50 & EMA 200 (Trend)
- RSI 14 (Pullback & Momentum)
- ATR 14 (Volatility & Stop Loss)
Test to see if save is working

This is to check if save is working, attempt 4
Rename test 1, rename working
Versioning Test 1
"""

import backtrader as bt


class TrendPullbackStrategy(bt.Strategy):
    """
    Trend + Pullback Momentum Strategy (Daily)
    ------------------------------------------
    A strategy that buys/sells pullbacks in an established trend.

    Parameters:
    - ema_fast (int): Period for fast EMA (default: 50)
    - ema_slow (int): Period for slow EMA (default: 200)
    - rsi_period (int): Period for RSI (default: 14)
    - atr_period (int): Period for ATR (default: 14)
    - atr_avg_period (int): Period for SMA of ATR (default: 20)
    
    Filters & Thresholds:
    - pullback_pct (float): Max distance from EMA50 to be considered a pullback (default: 0.02 / 2%)
    - max_gap_pct (float): Max allowed gap at open to avoid runaway trades (default: 0.03 / 3%)
    - min_trend_diff_pct (float): Min distance between EMA50 and EMA200 (default: 0.01 / 1%)
    - atr_sl_mult (float): ATR multiplier for Stop Loss (default: 1.5)
    - rr_ratio (float): Risk:Reward ratio for target calculation (default: 2.0)
    - risk_pct (float): Portfolio fraction risked per trade (default: 0.015 / 1.5%)
    - use_trailing_sl (bool): Whether to trail SL via prev day high/low (default: False)
    """

    params = dict(
        ema_fast=20,              
        ema_slow=50,
        rsi_period=14,
        atr_period=14,
        atr_avg_period=20,
        pullback_pct=0.03,        
        rsi_long_lower=55,        
        rsi_short_upper=45,       
        rsi_long_exit=65,         
        rsi_short_exit=35,        
        atr_sl_mult=3.5,          
        rr_ratio=5.0,             
        risk_pct=0.015,           
        max_gap_pct=0.04,         
        min_trend_diff_pct=0.01,
        allow_short_selling=True,
        use_trailing_sl=False,    
    )

    def __init__(self):
        # Data References
        self.o = self.data.open
        self.h = self.data.high
        self.l = self.data.low
        self.c = self.data.close

        # Indicators
        self.ema50 = bt.indicators.EMA(self.c, period=self.p.ema_fast)
        self.ema200 = bt.indicators.EMA(self.c, period=self.p.ema_slow)
        self.rsi = bt.indicators.RSI(self.c, period=self.p.rsi_period)
        self.atr = bt.indicators.ATR(self.data, period=self.p.atr_period)

        # Order Tracking
        self.order = None
        self.entry_price = None
        self.sl_price = None
        self.tp_price = None

    def log(self, txt, dt=None):
        """Logging function for strategy."""
        dt = dt or self.data.datetime.date(0)
        print(f"[{dt}] {txt}")

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:
            side = "BUY" if order.isbuy() else "SELL"
            price = order.executed.price
            size = order.executed.size
            self.log(f"{side} EXECUTED, Price: {price:.2f}, Size: {size}")
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f"Order {order.getstatusname()}")

        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        sign = "+" if trade.pnl >= 0 else ""
        self.log(f"TRADE CLOSED | PnL: {sign}{trade.pnl:.2f} | Bars: {trade.barlen}")
        self.sl_price = None
        self.tp_price = None
        self.entry_price = None

    def _calc_position_size(self, stop_distance):
        """Calculate position size based on risking a percentage of the portfolio."""
        if stop_distance <= 0:
            return 1
        risk_amt = self.broker.getvalue() * self.p.risk_pct
        return max(1, int(risk_amt / stop_distance))

    def next(self):
        # Wait until all indicators have enough data
        if len(self) < self.p.ema_slow:
            return

        # Do nothing if an order is pending
        if self.order:
            return

        # Manage open positions
        if self.position:
            self._manage_position()
            return

        # ============================================
        # FILTERS
        # ============================================
        
        # 1. Avoid sideways markets (EMA distance filter)
        ema_diff_pct = abs(self.ema50[0] - self.ema200[0]) / self.ema200[0]
        if ema_diff_pct < self.p.min_trend_diff_pct:
            return  # Sideways market

        # 2. Gap filter 
        prev_close = self.c[-1]
        gap_pct = abs(self.o[0] - prev_close) / prev_close
        if gap_pct > self.p.max_gap_pct:
            return  # Gap too large

        # ============================================
        # TREND & ENTRY CONDITIONS
        # ============================================

        price = self.c[0]
        is_green = self.c[0] > self.o[0]
        is_red = self.c[0] < self.o[0]
        
        # Momentum check: instead of a hard exact-bar CrossUp, we check if RSI is bouncing from a low level
        has_momentum_long = (self.rsi[0] > self.rsi[-1]) and (self.rsi[-1] < self.p.rsi_long_lower)
        has_momentum_short = (self.rsi[0] < self.rsi[-1]) and (self.rsi[-1] > self.p.rsi_short_upper)

        # LONG RULES
        uptrend = (self.ema50[0] > self.ema200[0]) and (price > self.ema50[0])
        # Force the candle's LOW to touch or get very close to the EMA50 (true bounce)
        touched_ema_long = self.l[0] < (self.ema50[0] * (1.0 + self.p.pullback_pct))
        
        if uptrend and touched_ema_long and is_green and has_momentum_long:
            sl_dist = self.p.atr_sl_mult * self.atr[0]
            sl = price - sl_dist
            tp = price + (sl_dist * self.p.rr_ratio)
            size = self._calc_position_size(sl_dist)
            
            self.log(f"LONG ENTRY SIGNAL | Close: {price:.2f} | SL: {sl:.2f} | TP: {tp:.2f}")
            self.order = self.buy(size=size)
            self.sl_price = sl
            self.tp_price = tp
            self.entry_price = price
            return

        # SHORT RULES
        downtrend = (self.ema50[0] < self.ema200[0]) and (price < self.ema50[0])
        # Force the candle's HIGH to touch or get very close to the EMA50 (true rejection)
        touched_ema_short = self.h[0] > (self.ema50[0] * (1.0 - self.p.pullback_pct))
        
        if downtrend and touched_ema_short and is_red and has_momentum_short:
            sl_dist = self.p.atr_sl_mult * self.atr[0]
            sl = price + sl_dist
            tp = price - (sl_dist * self.p.rr_ratio)
            size = self._calc_position_size(sl_dist)

            self.log(f"SHORT ENTRY SIGNAL | Close: {price:.2f} | SL: {sl:.2f} | TP: {tp:.2f}")
            self.order = self.sell(size=size)
            self.sl_price = sl
            self.tp_price = tp
            self.entry_price = price
            return

    def _manage_position(self):
        """Handles Take Profit, Stop Loss, Trailing SL, and RSI Exits."""
        price = self.c[0]
        
        if self.position.size > 0:  # LONG
            # Trail SL handling
            if self.p.use_trailing_sl:
                trail_sl = self.l[-1]  # Previous day low
                if trail_sl > self.sl_price and trail_sl < price:
                    self.sl_price = trail_sl
            
            # Exits
            if price <= self.sl_price:
                self.log(f"LONG SL HIT at {price:.2f}")
                self.close()
            elif price >= self.tp_price:
                self.log(f"LONG TP HIT at {price:.2f}")
                self.close()
            elif self.rsi[0] > self.p.rsi_long_exit:
                self.log(f"LONG RSI EXIT at {price:.2f} (RSI={self.rsi[0]:.2f})")
                self.close()
                
        elif self.position.size < 0:  # SHORT
            # Trail SL handling
            if self.p.use_trailing_sl:
                trail_sl = self.h[-1]  # Previous day high
                if trail_sl < self.sl_price and trail_sl > price:
                    self.sl_price = trail_sl
                    
            # Exits
            if price >= self.sl_price:
                self.log(f"SHORT SL HIT at {price:.2f}")
                self.close()
            elif price <= self.tp_price:
                self.log(f"SHORT TP HIT at {price:.2f}")
                self.close()
            elif self.rsi[0] < self.p.rsi_short_exit:
                self.log(f"SHORT RSI EXIT at {price:.2f} (RSI={self.rsi[0]:.2f})")
                self.close()
