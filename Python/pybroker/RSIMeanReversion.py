import numpy as np
from pybroker import Strategy, StrategyConfig, ExecContext
from pybroker.data import DataSource
import os
import pandas as pd
import sys

# 添加AI工具路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class CryptoCSVDataSource(DataSource):
    """自定义CSV数据源适配器"""

    def __init__(self, csv_file='crypto_data_export.csv'):
        super().__init__()
        self.csv_file = csv_file
        # 验证文件是否存在
        if not os.path.exists(csv_file):
            raise FileNotFoundError(f"数据文件 {csv_file} 不存在")

    def _fetch_data(self, symbols, start_date, end_date, timeframe, adjust):
        """
        PyBroker数据源查询接口
        :param symbols: 交易标的列表
        :param start_date: 开始日期
        :param end_date: 结束日期
        :param timeframe: 时间周期
        :param adjust: 是否复权
        :return: 格式化的DataFrame
        """
        try:
            # 读取CSV文件
            df = pd.read_csv(self.csv_file)

            # 确保日期列是datetime格式
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])

            # 如果没有symbol列，添加默认symbol
            if 'symbol' not in df.columns:
                df['symbol'] = 'BTCUSDT'  # 默认加密货币对

            # 过滤交易标的
            if symbols:
                if isinstance(symbols, str):
                    symbols = [symbols]
                df = df[df['symbol'].isin(symbols)]

            # 过滤日期范围
            if 'date' in df.columns:
                df = df[(df['date'] >= pd.to_datetime(start_date)) &
                        (df['date'] <= pd.to_datetime(end_date))]

            # 确保包含所有必需的列
            required_columns = ['symbol', 'date', 'open', 'high', 'low', 'close', 'volume']
            for col in required_columns:
                if col not in df.columns:
                    raise ValueError(f"CSV文件缺少必需的列: {col}")

            # 如果没有volume列，添加默认值
            if 'volume' not in df.columns:
                df['volume'] = 1000000

            print(f"成功加载 {len(df)} 行数据")
            return df

        except Exception as e:
            print(f"从CSV文件加载数据失败: {e}")
            # 返回空的DataFrame，包含必需的列
            return pd.DataFrame(columns=['symbol', 'date', 'open', 'high', 'low', 'close', 'volume'])


def rsi_mean_reversion_strategy(ctx: ExecContext):
    # RSI参数设置
    rsi_period = 14
    rsi_overbought = 70
    rsi_oversold = 30

    # 布林带参数设置
    bb_period = 20
    bb_std = 2

    # 获取历史收盘价数据
    close_prices = ctx.close

    # 确保有足够的数据计算指标
    if len(close_prices) < max(rsi_period + 1, bb_period):
        return

    # 计算RSI指标
    deltas = np.diff(close_prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    avg_gain = np.mean(gains[-rsi_period:])
    avg_loss = np.mean(losses[-rsi_period:])

    if avg_loss == 0:
        rsi = 100
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

    # 计算布林带指标
    bb_middle = np.mean(close_prices[-bb_period:])
    bb_std_dev = np.std(close_prices[-bb_period:])
    bb_upper = bb_middle + (bb_std_dev * bb_std)
    bb_lower = bb_middle - (bb_std_dev * bb_std)
    bb_percent = (close_prices[-1] - bb_lower) / (bb_upper - bb_lower) if (bb_upper - bb_lower) != 0 else 0

    # 获取当前持仓信息
    current_position = ctx.long_pos()

    # 买入信号：RSI超卖且价格接近布林带下轨(均值回归)
    if (rsi < rsi_oversold and bb_percent < 0.2) and not current_position:
        # 买入信号，使用市价单买入
        ctx.buy_shares = ctx.calc_target_shares(1)  # 使用全部资金
        ctx.buy_limit_price = ctx.close[-1]  # 市价买入

    # 卖出信号：RSI超买且价格接近布林带上轨(均值回归)
    elif (rsi > rsi_overbought and bb_percent > 0.8) and current_position:
        # 卖出信号，卖出所有持仓
        ctx.sell_all_shares()


# 创建CSV数据源实例
try:
    csv_data_source = CryptoCSVDataSource('crypto_data_export.csv')
    print("成功创建CSV数据源")
except FileNotFoundError as e:
    print(f"错误: {e}")
    print("请确保 crypto_data_export.csv 文件存在于当前目录")
    exit(1)

# 策略配置
config = StrategyConfig(
    initial_cash=500_000,
    enable_fractional_shares=True  # 启用小数股数
)

# 创建策略实例
strategy = Strategy(
    data_source=csv_data_source,
    start_date='20220901',
    end_date='20240905',
    config=config,
)

# 添加执行函数
strategy.add_execution(
    fn=rsi_mean_reversion_strategy,
    symbols=['BTCUSDT']
)

# 执行回测
try:
    print("开始执行回测...")
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