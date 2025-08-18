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


def sma_cross_strategy(ctx: ExecContext):
    # 计算双均线
    short_term = 10
    long_term = 60*24

    # 获取历史收盘价数据
    close_prices = ctx.close

    # 确保有足够的数据计算均线
    if len(close_prices) < long_term:
        return

    # 计算移动平均线
    short_ma = close_prices[-short_term:].mean()
    long_ma = close_prices[-long_term:].mean()
    # print(short_ma, long_ma)

    # 获取当前持仓信息
    current_position = ctx.long_pos()
    # print(current_position)

    # 买入信号：短期均线上穿长期均线且当前无持仓
    if short_ma > long_ma and not current_position:
        # 买入信号，使用市价单买入
        ctx.buy_shares = ctx.calc_target_shares(1) # 使用全部资金
        ctx.buy_limit_price = ctx.close[-1] # 市价买入

    # 卖出信号：短期均线下穿长期均线且当前有持仓
    elif short_ma < long_ma and current_position:
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
    fn=sma_cross_strategy,
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