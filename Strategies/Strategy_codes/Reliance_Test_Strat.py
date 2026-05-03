import backtrader as bt


class RelianceIntradayVWAPBreakoutStrategy(bt.Strategy):
    params = dict(
        ema_fast=9,
        ema_slow=21,
        rsi_period=14,
        atr_period=14,
        vol_period=20,
        rsi_long_min=55,
        rsi_short_max=45,
        atr_sl_mult=1.2,
        rr_ratio=2.0,
        risk_pct=0.01,
        max_bars_in_trade=18,
        allow_short_selling=True,
    )

    def __init__(self):
        self.o = self.data.open
        self.h = self.data.high
        self.l = self.data.low
        self.c = self.data.close
        self.v = self.data.volume

        self.ema_fast = bt.indicators.EMA(self.c, period=self.p.ema_fast)
        self.ema_slow = bt.indicators.EMA(self.c, period=self.p.ema_slow)
        self.rsi = bt.indicators.RSI(self.c, period=self.p.rsi_period)
        self.atr = bt.indicators.ATR(self.data, period=self.p.atr_period)
        self.vol_sma = bt.indicators.SMA(self.v, period=self.p.vol_period)

        self.order = None
        self.entry_price = None
        self.sl_price = None
        self.tp_price = None
        self.entry_bar = None

    def _calc_position_size(self, stop_distance):
        if stop_distance <= 0:
            return 1
        risk_amt = self.broker.getvalue() * self.p.risk_pct
        return max(1, int(risk_amt / stop_distance))

    def next(self):
        if len(self) < max(self.p.ema_slow, self.p.vol_period, self.p.atr_period):
            return

        if self.order:
            return

        if self.position:
            self._manage_position()
            return

        price = self.c[0]
        strong_volume = self.v[0] > self.vol_sma[0]
        bullish_candle = self.c[0] > self.o[0]
        bearish_candle = self.c[0] < self.o[0]

        long_trend = self.ema_fast[0] > self.ema_slow[0]
        short_trend = self.ema_fast[0] < self.ema_slow[0]

        long_breakout = self.c[0] > max(self.h[-1], self.ema_fast[0])
        short_breakdown = self.c[0] < min(self.l[-1], self.ema_fast[0])

        long_entry = (
            long_trend
            and long_breakout
            and bullish_candle
            and strong_volume
            and self.rsi[0] >= self.p.rsi_long_min
        )

        short_entry = (
            self.p.allow_short_selling
            and short_trend
            and short_breakdown
            and bearish_candle
            and strong_volume
            and self.rsi[0] <= self.p.rsi_short_max
        )

        if long_entry:
            sl_dist = self.atr[0] * self.p.atr_sl_mult
            self.sl_price = price - sl_dist
            self.tp_price = price + sl_dist * self.p.rr_ratio
            self.entry_price = price
            self.entry_bar = len(self)
            size = self._calc_position_size(sl_dist)
            self.order = self.buy(size=size)

        elif short_entry:
            sl_dist = self.atr[0] * self.p.atr_sl_mult
            self.sl_price = price + sl_dist
            self.tp_price = price - sl_dist * self.p.rr_ratio
            self.entry_price = price
            self.entry_bar = len(self)
            size = self._calc_position_size(sl_dist)
            self.order = self.sell(size=size)

    def _manage_position(self):
        price = self.c[0]
        bars_held = len(self) - self.entry_bar if self.entry_bar is not None else 0

        if self.position.size > 0:
            if price <= self.sl_price:
                self.close()
            elif price >= self.tp_price:
                self.close()
            elif self.ema_fast[0] < self.ema_slow[0]:
                self.close()
            elif bars_held >= self.p.max_bars_in_trade:
                self.close()

        elif self.position.size < 0:
            if price >= self.sl_price:
                self.close()
            elif price <= self.tp_price:
                self.close()
            elif self.ema_fast[0] > self.ema_slow[0]:
                self.close()
            elif bars_held >= self.p.max_bars_in_trade:
                self.close()

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        self.order = None

    def notify_trade(self, trade):
        if trade.isclosed:
            self.entry_price = None
            self.sl_price = None
            self.tp_price = None
            self.entry_bar = None