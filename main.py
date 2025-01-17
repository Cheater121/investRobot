import datetime


from robotlib.robot import TradingRobotFactory
from robotlib.strategy import TradeStrategyParams, MAEStrategy
from robotlib.vizualization import Visualizer
from config_data.config import load_config


config = load_config()

token = config.tcs_client.token
account_id = config.tcs_client.id


def backtest(robot):
    stats = robot.backtest(
        TradeStrategyParams(instrument_balance=0, currency_balance=15000, pending_orders=[]),
        train_duration=datetime.timedelta(days=5), test_duration=datetime.timedelta(days=30))
    stats.save_to_file('backtest_stats.pickle')


def trade(robot):
    stats = robot.trade()
    stats.save_to_file('stats.pickle')


def main():
    robot_factory = TradingRobotFactory(token=token, account_id=account_id, ticker='YNDX', class_code='TQBR',
                                        logger_level='INFO')
    robot = robot_factory.create_robot(MAEStrategy(visualizer=Visualizer('YNDX', 'RUB')), sandbox_mode=True)

    backtest(robot)

    trade(robot)


if __name__ == '__main__':
    main()