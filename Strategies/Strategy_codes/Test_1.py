import backtrader as bt

class Test_1(bt.Strategy):
    def next(self):
        if not self.position:
            self.buy(size=1)
