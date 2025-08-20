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
    """
    使用K线看涨/看跌吞没形态(Engulfing Pattern) + OBV成交量均线交叉(OBV Cross)的策略
    """
    # 确保有足够的数据计算指标
    min_bars = 20  # 需要至少20根K线来计算指标
    if len(ctx.close) < min_bars:
        return

    # 获取OHLCV数据
    open_prices = ctx.open
    high_prices = ctx.high
    low_prices = ctx.low
    close_prices = ctx.close
    volumes = ctx.volume

    # 计算OBV (On-Balance Volume)
    obv = np.zeros(len(close_prices))
    obv[0] = volumes[0]
    for i in range(1, len(close_prices)):
        if close_prices[i] > close_prices[i - 1]:
            obv[i] = obv[i - 1] + volumes[i]
        elif close_prices[i] < close_prices[i - 1]:
            obv[i] = obv[i - 1] - volumes[i]
        else:
            obv[i] = obv[i - 1]

    # 计算OBV均线 (使用5日均线，更灵敏)
    obv_period = 5
    if len(obv) >= obv_period:
        obv_ma = np.zeros(len(obv))
        for i in range(obv_period - 1, len(obv)):
            obv_ma[i] = np.mean(obv[i - (obv_period - 1):i + 1])
    else:
        return  # 数据不足，无法计算OBV均线

    # 打印调试信息
    if len(ctx.close) > 30:
        print(f"当前价格: {close_prices[-1]}, 前一价格: {close_prices[-2]}")
        print(f"当前OBV: {obv[-1]}, OBV均线: {obv_ma[-1]}")
        print(f"前一OBV: {obv[-2]}, 前一OBV均线: {obv_ma[-2]}")

    # 获取当前持仓信息
    current_position = ctx.long_pos()

    # 检测看涨吞没形态 (Bullish Engulfing) - 放宽条件
    bullish_engulfing = (
            close_prices[-2] < open_prices[-2] and  # 前一根为阴线
            close_prices[-1] > open_prices[-1] and  # 当前为阳线
            (open_prices[-1] < close_prices[-2] or abs(open_prices[-1] - close_prices[-2]) < 0.01 * close_prices[
                -2]) and  # 当前开盘价接近或低于前一根收盘价
            (close_prices[-1] > open_prices[-2] or abs(close_prices[-1] - open_prices[-2]) < 0.01 * open_prices[-2])
    # 当前收盘价接近或高于前一根开盘价
    )

    # 检测看跌吞没形态 (Bearish Engulfing) - 放宽条件
    bearish_engulfing = (
            close_prices[-2] > open_prices[-2] and  # 前一根为阳线
            close_prices[-1] < open_prices[-1] and  # 当前为阴线
            (open_prices[-1] > close_prices[-2] or abs(open_prices[-1] - close_prices[-2]) < 0.01 * close_prices[
                -2]) and  # 当前开盘价接近或高于前一根收盘价
            (close_prices[-1] < open_prices[-2] or abs(close_prices[-1] - open_prices[-2]) < 0.01 * open_prices[-2])
    # 当前收盘价接近或低于前一根开盘价
    )

    # 检测OBV与均线交叉 - 放宽条件，考虑接近交叉的情况
    # 金叉：OBV从下方穿过或接近OBV均线
    obv_golden_cross = (
            (obv[-2] < obv_ma[-2] and obv[-1] > obv_ma[-1]) or  # 严格金叉
            (obv[-2] < obv_ma[-2] and abs(obv[-1] - obv_ma[-1]) < 0.005 * obv_ma[-1])  # 接近金叉
    )

    # 死叉：OBV从上方穿过或接近OBV均线
    obv_death_cross = (
            (obv[-2] > obv_ma[-2] and obv[-1] < obv_ma[-1]) or  # 严格死叉
            (obv[-2] > obv_ma[-2] and abs(obv[-1] - obv_ma[-1]) < 0.005 * obv_ma[-1])  # 接近死叉
    )

    # 单独条件判断 - 用于调试
    if bullish_engulfing:
        print(f"检测到看涨吞没形态")
    if obv_golden_cross:
        print(f"检测到OBV金叉")
    if bearish_engulfing:
        print(f"检测到看跌吞没形态")
    if obv_death_cross:
        print(f"检测到OBV死叉")

    # 买入信号：看涨吞没形态 + OBV金叉
    if (bullish_engulfing and obv_golden_cross):
        if not current_position:
            print(f"生成买入信号！当前价格: {close_prices[-1]}")
            # 买入信号，使用市价单买入
            ctx.buy_shares = ctx.calc_target_shares(1)  # 使用全部资金
            ctx.buy_limit_price = ctx.close[-1]  # 市价买入

    # 卖出信号：看跌吞没形态 + OBV死叉
    elif (bearish_engulfing and obv_death_cross):
        if current_position:
            print(f"生成卖出信号！当前价格: {close_prices[-1]}")
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
