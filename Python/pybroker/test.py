# file: csv_strategy.py
import pandas as pd
import numpy as np
from pybroker import Strategy, ExecContext, StrategyConfig
from pybroker.indicator import Indicator

# 定义自定义指标：移动平均线
def moving_average(data, period):
    """计算简单移动平均线"""
    return data.rolling(window=period).mean()

# 创建自定义指标
# 修改Indicator的初始化参数，正确传递参数
sma_20 = Indicator('sma_20', lambda data: moving_average(data.close, 20), {})
sma_50 = Indicator('sma_50', lambda data: moving_average(data.close, 50), {})

def trade_rule(ctx: ExecContext):
    """交易规则：包含买入和卖出逻辑"""
    # 获取指标值
    sma20 = ctx.indicator('sma_20')
    sma50 = ctx.indicator('sma_50')

    # 检查是否有足够的数据
    if len(sma20) < 2 or len(sma50) < 2:
        return

    # 买入条件：短期均线上穿长期均线
    if sma20[-2] <= sma50[-2] and sma20[-1] > sma50[-1]:
        ctx.buy_all_shares()
    # 卖出条件：短期均线下穿长期均线
    elif sma20[-2] >= sma50[-2] and sma20[-1] < sma50[-1]:
        ctx.sell_all_shares()

# 创建CSV数据源实例
try:
    df = pd.read_csv('crypto_data_export.csv')
    # 将日期列转换为datetime类型
    df['date'] = pd.to_datetime(df['date'])
    print("成功读取CSV数据")
except FileNotFoundError as e:
    print(f"错误: {e}")
    print("请确保 crypto_data_export.csv 文件存在于当前目录")
    exit(1)

# 策略配置 - 使用支持的参数
# 一天为间隔
config = StrategyConfig(
    initial_cash=500_000
)

# 创建策略实例
strategy = Strategy(
    data_source=df,
    start_date='20220901',
    end_date='20240905',
    config=config
)

# 添加指标到策略
strategy.add_indicator(sma_20)
strategy.add_indicator(sma_50)

# 添加执行函数 - 使用加密货币标的
strategy.add_execution(
    fn=trade_rule,
    symbols=['BTCUSDT']  # 根据您的数据调整交易标的
)

# 执行回测
try:
    print("开始执行回测...")
    # 按天跑
    result = strategy.backtest(
        timeframe='1d',
    )


    # 输出结果
    print("\n=== 回测指标 ===")
    print(result.metrics_df)

    print("\n=== 交易订单 ===")
    print(result.orders)

    print("\n=== 持仓情况 ===")
    print(result.positions)

    print("\n=== 投资组合 ===")
    print(result.portfolio)

    print("\n=== 交易详情 ===")
    print(result.trades)

except Exception as e:
    print(f"回测执行失败: {e}")
    import traceback

    traceback.print_exc()