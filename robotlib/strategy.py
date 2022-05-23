import datetime
import math
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from tinkoff.invest import Candle, HistoricCandle, Quotation, Instrument, OrderType, OrderDirection, OrderState,\
    SubscriptionInterval, MarketDataResponse
from robotlib.money import Money


@dataclass
class TradeStrategyParams:
    instrument_balance: int
    currency_balance: float
    pending_orders: list[OrderState]


@dataclass
class RobotTradeOrder:
    quantity: int
    direction: OrderDirection
    price: Money | None = None
    order_type: OrderType = OrderType.ORDER_TYPE_MARKET


@dataclass
class StrategyDecision:
    robot_trade_order: RobotTradeOrder | None = None
    cancel_orders: list[OrderState] = field(default_factory=list)


class TradeStrategyBase(ABC):
    instrument_info: Instrument

    @property
    @abstractmethod
    def candle_subscription_interval(self) -> SubscriptionInterval:
        return SubscriptionInterval.SUBSCRIPTION_INTERVAL_ONE_MINUTE

    @property
    @abstractmethod
    def order_book_subscription_depth(self) -> int | None:  # set not None to subscribe robot to order book
        return None

    @property
    @abstractmethod
    def trades_subscription(self) -> bool:  # set True to subscribe robot to trades stream
        return False

    @property
    @abstractmethod
    def strategy_id(self) -> str:  # string representing short strategy name for logger
        raise NotImplementedError()

    def load_instrument_info(self, instrument_info: Instrument):
        self.instrument_info = instrument_info

    def load_candles(self, candles: list[HistoricCandle]) -> None:
        """
        Method used by robot to load historic data
        """
        pass

    @abstractmethod
    def decide(self, market_data: MarketDataResponse, params: TradeStrategyParams) -> StrategyDecision:
        if market_data.candle:
            return self.decide_by_candle(market_data.candle, params)

    @abstractmethod
    def decide_by_candle(self, candle: Candle | HistoricCandle, params: TradeStrategyParams) -> StrategyDecision:
        pass


class RandomStrategy(TradeStrategyBase):
    request_candles: bool = True
    strategy_id: str = 'random'

    def __init__(self, lo: int, hi: int):
        self.lo = lo
        self.hi = hi

    def decide(self, candle: Candle | HistoricCandle, params: TradeStrategyParams) -> RobotTradeOrder | None:
        lo = max(self.lo, -params.instrument_balance)
        hi = min(self.hi, math.floor(params.currency_balance / self.convert_quotation(candle.close)))

        quantity = random.randint(lo, hi)
        direction = OrderDirection.ORDER_DIRECTION_BUY if quantity > 0 else OrderDirection.ORDER_DIRECTION_SELL

        return RobotTradeOrder(quantity=quantity, direction=direction)

    @staticmethod
    def convert_quotation(amount: Quotation) -> float | None:
        if amount is None:
            return None
        return amount.units + amount.nano / (10 ** 9)


class MAEStrategy(TradeStrategyBase):
    request_candles: bool = True
    strategy_id: str = 'mae'

    short_len: int
    long_len: int
    trade_count: int
    prices = dict[datetime.datetime, Money]
    prev_sign: bool

    def __init__(self, short_len: int = 5, long_len: int = 20, trade_count: int = 1):
        assert long_len > short_len
        self.short_len = short_len
        self.long_len = long_len
        self.trade_count = trade_count
        self.prices = {}

    def load_candles(self, candles: list[HistoricCandle]) -> None:
        self.prices = {candle.time.replace(second=0, microsecond=0): Money(candle.close)
                       for candle in candles[-self.long_len:]}
        self.prev_sign = self._long_avg() > self._short_avg()

    def decide(self, candle: Candle | HistoricCandle, params: TradeStrategyParams) -> StrategyDecision:
        time: datetime = candle.time.replace(second=0, microsecond=0)
        order: RobotTradeOrder | None = None
        if time not in self.prices:  # make order only once a minute (when minutely candle is ready)
            sign = self._long_avg() > self._short_avg()
            if sign != self.prev_sign:
                if sign:
                    if params.instrument_balance > 0:
                        order = RobotTradeOrder(quantity=min(self.trade_count, params.instrument_balance),
                                                direction=OrderDirection.ORDER_DIRECTION_SELL)
                else:
                    lot_price = Money(candle.close).to_float() * self.instrument_info.lot
                    if params.currency_balance >= lot_price:
                        order = RobotTradeOrder(quantity=min(self.trade_count, int(params.currency_balance / lot_price)),
                                                direction=OrderDirection.ORDER_DIRECTION_BUY)

            self.prev_sign = sign
        self.prices[time] = Money(candle.close)
        return StrategyDecision(robot_trade_order=order)

    def get_prices_list(self) -> list[Money]:
        # sort by keys and then convert to a list of values
        return list(map(lambda x: x[1], sorted(self.prices.items(), key=lambda x: x[0])))

    def _long_avg(self):
        return sum(float(price) for price in self.get_prices_list()[-self.long_len:]) / self.long_len

    def _short_avg(self):
        return sum(float(price) for price in self.get_prices_list()[-self.short_len:]) / self.short_len
