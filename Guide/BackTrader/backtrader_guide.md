# BackTrader Quick Reference

## Core Workflow

```
Strategy → Cerebro → Data Feed → cerebro.run() → cerebro.plot()
```

1. Create a `Strategy` (indicators, logic, order handling)
2. Instantiate `Cerebro`
3. Add strategy: `cerebro.addstrategy(MyStrategy)`
4. Load & add data: `cerebro.adddata(data)`
5. Configure broker (cash, commission, sizer)
6. Run: `cerebro.run()`
7. Plot (optional): `cerebro.plot()`

---

## Minimal Setup

```python
import backtrader as bt

cerebro = bt.Cerebro()
cerebro.broker.setcash(100000.0)
cerebro.run()
print('Final Portfolio Value: %.2f' % cerebro.broker.getvalue())
```

---

## Loading a Data Feed

```python
import datetime
import backtrader as bt

data = bt.feeds.YahooFinanceCSVData(
    dataname='path/to/data.csv',
    fromdate=datetime.datetime(2000, 1, 1),
    todate=datetime.datetime(2000, 12, 31),
    reverse=False)   # True if CSV is date-descending (Yahoo online)

cerebro = bt.Cerebro()
cerebro.adddata(data)
```

---

## Strategy Structure

```python
class MyStrategy(bt.Strategy):
    params = (
        ('maperiod', 15),
        ('printlog', False),
    )

    def log(self, txt, dt=None, doprint=False):
        if self.params.printlog or doprint:
            dt = dt or self.datas[0].datetime.date(0)
            print('%s, %s' % (dt.isoformat(), txt))

    def __init__(self):
        self.dataclose = self.datas[0].close
        self.order = None
        self.buyprice = None
        self.buycomm = None
        self.sma = bt.indicators.SimpleMovingAverage(
            self.datas[0], period=self.params.maperiod)

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.log('BUY EXECUTED, Price: %.2f, Cost: %.2f, Comm %.2f' %
                         (order.executed.price, order.executed.value, order.executed.comm))
                self.buyprice = order.executed.price
                self.buycomm = order.executed.comm
            else:
                self.log('SELL EXECUTED, Price: %.2f, Cost: %.2f, Comm %.2f' %
                         (order.executed.price, order.executed.value, order.executed.comm))
            self.bar_executed = len(self)

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('Order Canceled/Margin/Rejected')

        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        self.log('OPERATION PROFIT, GROSS %.2f, NET %.2f' % (trade.pnl, trade.pnlcomm))

    def next(self):
        self.log('Close, %.2f' % self.dataclose[0])

        if self.order:
            return

        if not self.position:
            if self.dataclose[0] > self.sma[0]:
                self.log('BUY CREATE, %.2f' % self.dataclose[0])
                self.order = self.buy()
        else:
            if self.dataclose[0] < self.sma[0]:
                self.log('SELL CREATE, %.2f' % self.dataclose[0])
                self.order = self.sell()

    def stop(self):
        self.log('(MA Period %2d) Ending Value %.2f' %
                 (self.params.maperiod, self.broker.getvalue()), doprint=True)
```

---

## Broker Configuration

```python
cerebro.broker.setcash(1000.0)
cerebro.broker.setcommission(commission=0.001)  # 0.1%
cerebro.addsizer(bt.sizers.FixedSize, stake=10)
```

---

## Running a Strategy

```python
if __name__ == '__main__':
    cerebro = bt.Cerebro()
    cerebro.addstrategy(MyStrategy)

    data = bt.feeds.YahooFinanceCSVData(
        dataname='path/to/data.csv',
        fromdate=datetime.datetime(2000, 1, 1),
        todate=datetime.datetime(2000, 12, 31),
        reverse=False)

    cerebro.adddata(data)
    cerebro.broker.setcash(1000.0)
    cerebro.addsizer(bt.sizers.FixedSize, stake=10)
    cerebro.broker.setcommission(commission=0.001)

    print('Starting Portfolio Value: %.2f' % cerebro.broker.getvalue())
    cerebro.run()
    print('Final Portfolio Value: %.2f' % cerebro.broker.getvalue())
    cerebro.plot()
```

---

## Strategy Optimization

Use `optstrategy` instead of `addstrategy` to sweep parameter ranges:

```python
cerebro.optstrategy(MyStrategy, maperiod=range(10, 31))
cerebro.run(maxcpus=1)
```

The `stop()` hook prints results per parameter combination.

---

## Key Concepts

| Concept | Detail |
|---|---|
| `self.datas[0]` | Default data feed (system clock) |
| `self.datas[0].close` | Close line reference |
| `self.position` | Current open position (`None` if flat) |
| `self.order` | Track pending order to avoid duplicates |
| `self.bar_executed` | Bar index when last order was filled |
| `notify_order` | Called on every order status change |
| `notify_trade` | Called when a round-trip trade closes |
| `next()` | Called on each bar once indicators are ready |
| `stop()` | Called once when data is exhausted |

---

## Indicators

```python
# In __init__:
self.sma  = bt.indicators.SimpleMovingAverage(self.data, period=15)
self.ema  = bt.indicators.ExponentialMovingAverage(self.data, period=15)
self.rsi  = bt.indicators.RSI(self.data)
self.macd = bt.indicators.MACD(self.data)
self.bb   = bt.indicators.BollingerBands(self.data)
```

Indicators are auto-plotted by `cerebro.plot()`.

---

## Plotting

```python
cerebro.plot()                         # default
cerebro.plot(style='candlestick')      # candlestick chart
```