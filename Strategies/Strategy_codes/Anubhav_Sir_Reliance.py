import backtrader as bt
from datetime import time


PARAMETERS = dict(
    ema_period=20,
    vwap_period=75,
    volume_sma_period=20,
    volume_spike_mult=1.5,

    breakout_buffer_pct=0.0005,
    retest_buffer_pct=0.0015,

    option_sl_pct=0.25,
    rr_ratio=1.5,
    risk_pct=0.01,

    trade_start_time=time(9, 35),
    trade_end_time=time(14, 45),
    force_exit_time=time(15, 15),

    max_trades_per_day=3,
    max_losses_per_day=2,

    allow_short_selling=True,
)


class NiftyIntradayOptionBuyingStrategy(bt.Strategy):
    params = PARAMETERS

    def __init__(self):
        self.o = self.data.open
        self.h = self.data.high
        self.l = self.data.low
        self.c = self.data.close
        self.v = self.data.volume

        self.ema20 = bt.indicators.EMA(self.c, period=self.p.ema_period)
        self.vol_sma = bt.indicators.SMA(self.v, period=self.p.volume_sma_period)

        self.vwap = bt.indicators.SumN(self.c * self.v, period=self.p.vwap_period) / bt.indicators.SumN(
            self.v, period=self.p.vwap_period
        )

        self.order = None
        self.entry_price = None
        self.sl_price = None
        self.tp_price = None

        self.current_date = None
        self.pdh = None
        self.pdl = None
        self.day_high = None
        self.day_low = None

        self.trades_today = 0
        self.losses_today = 0

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        self.order = None

    def notify_trade(self, trade):
        if trade.isclosed:
            if trade.pnl < 0:
                self.losses_today += 1

            self.entry_price = None
            self.sl_price = None
            self.tp_price = None

    def _calc_position_size(self, stop_distance):
        if stop_distance <= 0:
            return 1

        risk_amount = self.broker.getvalue() * self.p.risk_pct
        return max(1, int(risk_amount / stop_distance))

    def _reset_day(self):
        today = self.data.datetime.date(0)

        if self.current_date != today:
            if self.day_high is not None and self.day_low is not None:
                self.pdh = self.day_high
                self.pdl = self.day_low

            self.current_date = today
            self.day_high = self.h[0]
            self.day_low = self.l[0]

            self.trades_today = 0
            self.losses_today = 0
        else:
            self.day_high = max(self.day_high, self.h[0])
            self.day_low = min(self.day_low, self.l[0])

    def next(self):
        if len(self) < max(self.p.ema_period, self.p.vwap_period, self.p.volume_sma_period):
            return

        self._reset_day()

        if self.order:
            return

        current_time = self.data.datetime.time(0)

        if self.position:
            self._manage_position()
            return

        if self.pdh is None or self.pdl is None:
            return

        if current_time < self.p.trade_start_time or current_time > self.p.trade_end_time:
            return

        if self.trades_today >= self.p.max_trades_per_day:
            return

        if self.losses_today >= self.p.max_losses_per_day:
            return

        price = self.c[0]
        prev_price = self.c[-1]

        volume_spike = self.v[0] > self.vol_sma[0] * self.p.volume_spike_mult

        above_vwap_ema = price > self.vwap[0] and price > self.ema20[0]
        below_vwap_ema = price < self.vwap[0] and price < self.ema20[0]

        pdh_breakout = (
            prev_price <= self.pdh
            and price > self.pdh * (1 + self.p.breakout_buffer_pct)
        )

        pdl_breakout = (
            prev_price >= self.pdl
            and price < self.pdl * (1 - self.p.breakout_buffer_pct)
        )

        pdh_retest_hold = (
            self.l[0] <= self.pdh * (1 + self.p.retest_buffer_pct)
            and price > self.pdh
        )

        pdl_retest_hold = (
            self.h[0] >= self.pdl * (1 - self.p.retest_buffer_pct)
            and price < self.pdl
        )

        call_entry = (
            (pdh_breakout or pdh_retest_hold)
            and above_vwap_ema
            and volume_spike
        )

        put_entry = (
            (pdl_breakout or pdl_retest_hold)
            and below_vwap_ema
            and volume_spike
        )

        if call_entry:
            sl_dist = price * self.p.option_sl_pct
            self.entry_price = price
            self.sl_price = price - sl_dist
            self.tp_price = price + (sl_dist * self.p.rr_ratio)

            size = self._calc_position_size(sl_dist)
            self.order = self.buy(size=size)
            self.trades_today += 1
            return

        if put_entry and self.p.allow_short_selling:
            sl_dist = price * self.p.option_sl_pct
            self.entry_price = price
            self.sl_price = price + sl_dist
            self.tp_price = price - (sl_dist * self.p.rr_ratio)

            size = self._calc_position_size(sl_dist)
            self.order = self.sell(size=size)
            self.trades_today += 1
            return

    def _manage_position(self):
        price = self.c[0]
        current_time = self.data.datetime.time(0)

        if current_time >= self.p.force_exit_time:
            self.close()
            return

        if self.position.size > 0:
            if price <= self.sl_price:
                self.close()
            elif price >= self.tp_price:
                self.close()
            elif price < self.pdh:
                self.close()
            elif price < self.vwap[0]:
                self.close()

        elif self.position.size < 0:
            if price >= self.sl_price:
                self.close()
            elif price <= self.tp_price:
                self.close()
            elif price > self.pdl:
                self.close()
            elif price > self.vwap[0]:
                self.close()