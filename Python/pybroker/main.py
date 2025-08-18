import pybroker as pb
from pybroker import Strategy, StrategyConfig, ExecContext
from pybroker.data import DataSource
import json
import os
import pandas as pd
from datetime import datetime
import sys

from Python.ai.prompt import call_ai_back_trade

# 添加AI工具路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from Python.ai.AIUtil import call_with_messages

    AI_AVAILABLE = True
except ImportError:
    print("警告: 无法导入AI模块，将使用文件决策")
    AI_AVAILABLE = False


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
            required_columns = ['symbol', 'date', 'open', 'high', 'low', 'close']
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


def execute_decision(ctx: ExecContext):
    """
    基于外部决策的交易执行函数
    """
    # 从AI或文件获取交易决策
    print("进行决策" ,ctx.date)
    decision = call_ai_back_trade(ctx.date)

    # 解析决策内容
    action = decision["action"]
    volume = float(decision["volume"])
    price = decision["price"] # 市价 或 具体金额
    reason = decision["reason"]

    # 当前状态
    symbol = ctx.symbol
    current_price = ctx.close[-1]  # 当前价格

    # 正确获取当前日期时间
    current_date = ctx.dt if hasattr(ctx, 'dt') else datetime.now()
    current_time = current_date.strftime('%Y-%m-%d %H:%M:%S') if hasattr(current_date, 'strftime') else str(
        current_date)

    # 记录决策日志
    log_str = f"[{symbol}] {current_time} - " \
              f"决策: {action} | 买入数量: {volume} | 价格: {price} | 原因: {reason}"
    print(log_str)
    
    # 执行交易操作
    if action == "买入" and volume > 0:
        # 计算可买数量
        buy_price = current_price if price == "市价" else float(price)

        # 验证价格有效性
        if buy_price <= 0:
            print(f"无效的买入价格: {buy_price}")
            return

        shares = volume / buy_price
        print(f"准备买入: {shares} 股，价格: {buy_price}")

        # 实际交易执行 - 调整为更直接的调用方式
        if price == "市价":
            # 使用更明确的市价买入方法
            ctx.buy_shares = shares
            print(f"已设置市价买入: {shares} 股")
        else:
            # 使用限价买入
            ctx.buy_limit_price = buy_price
            ctx.buy_shares = shares
            print(f"已设置限价买入: {shares} 股，限价: {buy_price}")

        # 设置持仓时间
        ctx.hold_bars = 3  # 默认持仓3个交易日

    elif action == "卖出" and volume > 0:
        # 确保有持仓可卖
        if not ctx.long_pos():
            print(f"[{symbol}] 没有持仓可卖")
            return

        # 计算可卖数量
        sell_price = current_price if price == "市价" else float(price)

        # 验证价格有效性
        if sell_price <= 0:
            print(f"无效的卖出价格: {sell_price}")
            return

        shares = min(ctx.shares, volume / sell_price)
        print(f"准备卖出: {shares} 股，价格: {sell_price}")

        # 实际交易执行 - 调整为更直接的调用方式
        if price == "市价":
            # 使用更明确的市价卖出方法
            ctx.sell_shares = shares
            print(f"已设置市价卖出: {shares} 股")
        else:
            # 使用限价卖出
            ctx.sell_limit_price = sell_price
            ctx.sell_shares = shares
            print(f"已设置限价卖出: {shares} 股，限价: {sell_price}")

    # 无论是否执行交易，都打印当前持仓信息，便于调试
    # 替换 ctx.shares 和 ctx.cash 为正确的API调用方式
    # try:
    #     # 尝试获取当前持仓数量和可用现金
    #     # PyBroker中通常使用不同的方式获取这些信息
    #     position = ctx.portfolio.get(ctx.symbol, {})
    #     shares = position.get('shares', 0) if position else 0
    #     cash = ctx.portfolio.cash if hasattr(ctx.portfolio, 'cash') else 0
    #     print(f"当前持仓: {shares} 股，可用现金: {cash}")
    # except Exception as e:
    #     print(f"获取持仓信息时出错: {e}")
    #     # 简化调试输出，避免因属性不存在导致回测失败
    #     print(f"当前决策: {action}")


# 创建CSV数据源实例
try:
    csv_data_source = CryptoCSVDataSource('crypto_data_export.csv')
    print("成功创建CSV数据源")
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
    data_source=csv_data_source,
    start_date='20230901',
    end_date='20230905',
    config=config,
)

# 添加执行函数 - 使用加密货币标的
strategy.add_execution(
    fn=execute_decision,
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
