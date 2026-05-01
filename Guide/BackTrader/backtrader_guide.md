# Backtrader Strategy Guide

This document is a cleaned, practical reference for working with `backtrader.Strategy`.
It focuses on the lifecycle, order APIs, notifications, and day-to-day usage patterns.

## 1) What a Strategy Is

In Backtrader, `Cerebro` is the engine and `Strategy` is your trading logic.
A strategy typically does three things:

1. Defines indicators and state in `__init__`
2. Generates actions in `next`
3. Reacts to broker updates in notify callbacks

---

## 2) Strategy Lifecycle

A strategy moves through this lifecycle during execution:

- `__init__`: create indicators, data aliases, state variables
- `start`: called once before bar processing starts
- `prenext`: called while indicators are not fully warmed up
- `nextstart`: called once when warm-up just completes
- `next`: called for normal bar-by-bar logic
- `stop`: called once when execution ends

### Minimal Example

```python
import backtrader as bt

class MyStrategy(bt.Strategy):
    params = dict(period=15)

    def __init__(self):
        self.sma = bt.indicators.SimpleMovingAverage(self.data.close, period=self.p.period)

    def next(self):
        if self.sma[0] > self.data.close[0]:
            pass
        elif self.sma[0] < self.data.close[0]:
            pass
```

---

## 3) Core Methods You Should Know

### `__init__(self)`
Use for:

- indicator creation
- static references (`self.data0`, `self.data1`, `self.dnames.xxx`)
- state initialization (`self.order`, counters, flags)

### `next(self)`
Use for:

- entries/exits
- signal checks
- position management

Important: it can be called multiple times for the same bar in replay/live scenarios.

### `notify_order(self, order)`
Triggered when order status changes (Submitted, Accepted, Completed, Canceled, Margin, Rejected).

Typical pattern:

```python
def notify_order(self, order):
    if order.status in [order.Completed]:
        action = "BUY" if order.isbuy() else "SELL"
        print(f"{action} EXECUTED @ {order.executed.price}")

    if order.status in [order.Completed, order.Canceled, order.Margin, order.Rejected]:
        self.order = None
```

### `notify_trade(self, trade)`
Triggered when a trade opens/updates/closes.

```python
def notify_trade(self, trade):
    if trade.isclosed:
        print(f"PnL Gross={trade.pnl:.2f}, Net={trade.pnlcomm:.2f}")
```

### `start(self)` / `stop(self)`
Good for setup/summary logging.

---

## 4) Order APIs (Buy / Sell / Close / Cancel)

### `buy(...)` and `sell(...)`
Both create and submit an order. They return an `Order` object.

Common parameters:

- `data`: which feed to trade (`None` means `self.data0`)
- `size`: quantity (if `None`, strategy sizer decides)
- `price`: trigger/limit price depending on order type
- `plimit`: limit price for `StopLimit`
- `exectype`: order type
- `valid`: order expiry
- `tradeid`: used internally to track overlapping trades
- `oco`: bind with another order in OCO group
- `parent`, `transmit`: used in bracket/grouped orders
- `trailamount`, `trailpercent`: for trailing stop variants

### `close(data=None, size=None, **kwargs)`
Closes existing position on target data.

### `cancel(order)`
Cancels a pending order.

---

## 5) Execution Types (`exectype`)

Common values:

- `Order.Market` (or `None`): execute at next available price
- `Order.Limit`: execute at limit price or better
- `Order.Stop`: trigger at stop, then market order
- `Order.StopLimit`: trigger at stop, then limit order
- `Order.Close`: execute on session close
- `Order.StopTrail`: trailing stop
- `Order.StopTrailLimit`: trailing stop + limit

---

## 6) Validity (`valid`) Options

- `None`: good-til-cancel behavior
- `datetime/date`: valid-until specific date/time
- `Order.DAY` / `0` / `timedelta()`: day order
- numeric matplotlib datetime value: valid-until that encoded time

---

## 7) Bracket and Target Helpers

### Bracket helpers

- `buy_bracket(...)`
- `sell_bracket(...)`

Used to place entry + protective stop + target orders as a managed group.

### Target helpers

- `order_target_size(data=None, target=0, **kwargs)`
- `order_target_value(data=None, target=0.0, price=None, **kwargs)`
- `order_target_percent(data=None, target=0.0, **kwargs)`

These rebalance toward a target exposure rather than issuing raw buy/sell quantities.

---

## 8) Useful Strategy Attributes

- `self.env`: owning `Cerebro`
- `self.datas`: all data feeds
- `self.data` / `self.data0`: first data feed
- `self.dataX`: alias for `self.datas[X]`
- `self.dnames`: named access to feeds
- `self.broker`: broker instance
- `self.position`: current position in `data0`
- `self.stats`: observers created for strategy
- `self.analyzers`: analyzers created for strategy

### Named data example

```python
# setup side
# cerebro.adddata(day_data, name='days')
# cerebro.resampledata(day_data, timeframe=bt.TimeFrame.Weeks, name='weeks')

# strategy side
smadays = bt.indicators.SMA(self.dnames.days, period=30)
smaweeks = bt.indicators.SMA(self.dnames.weeks, period=10)
```

---

## 9) Notification Hooks Beyond Orders/Trades

- `notify_cashvalue(cash, value)`: cash + portfolio value updates
- `notify_fund(cash, value, fundvalue, shares)`: fund-mode updates
- `notify_store(msg, *args, **kwargs)`: store/broker backend events
- `notify_timer(timer, when, *args, **kwargs)`: timer callback events

---

## 10) Practical Starter Template

```python
import backtrader as bt

class SmaCrossStrategy(bt.Strategy):
    params = dict(fast=20, slow=50)

    def __init__(self):
        self.fast = bt.indicators.SMA(self.data.close, period=self.p.fast)
        self.slow = bt.indicators.SMA(self.data.close, period=self.p.slow)
        self.cross = bt.indicators.CrossOver(self.fast, self.slow)
        self.order = None

    def next(self):
        if self.order:
            return

        if not self.position and self.cross[0] > 0:
            self.order = self.buy()
        elif self.position and self.cross[0] < 0:
            self.order = self.close()

    def notify_order(self, order):
        if order.status in [order.Completed, order.Canceled, order.Margin, order.Rejected]:
            self.order = None

    def notify_trade(self, trade):
        if trade.isclosed:
            print(f"Trade closed | Gross={trade.pnl:.2f} Net={trade.pnlcomm:.2f}")
```

---

## 11) Common Mistakes to Avoid

1. Using indicator objects directly instead of indexed values (`ind[0]`)
2. Placing duplicate orders because pending order state is not tracked
3. Ignoring warm-up phase (`prenext`) for long-period indicators
4. Assuming `next` runs exactly once per bar in replay/live modes
5. Not handling rejection/cancel/margin statuses in `notify_order`

---

## 12) Quick API List (Strategy)

- `next`, `nextstart`, `prenext`, `start`, `stop`
- `notify_order`, `notify_trade`, `notify_cashvalue`, `notify_fund`, `notify_store`, `notify_timer`
- `buy`, `sell`, `close`, `cancel`
- `buy_bracket`, `sell_bracket`
- `order_target_size`, `order_target_value`, `order_target_percent`
- `getsizer`, `setsizer`, `getsizing`
- `getposition`, `getpositionbyname`, `getpositionsbyname`
- `getdatanames`, `getdatabyname`
- `add_timer`

---

## 13) Notes for This Project

When integrating strategies into this codebase:

- keep strategy classes deterministic and stateless outside Backtrader-managed attributes
- avoid external side effects in `next` (file writes/network calls)
- prefer logging via the platform execution logging path, not ad-hoc prints in production runs

