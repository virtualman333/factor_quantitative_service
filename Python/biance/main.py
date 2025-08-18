# 导入Binance API客户端及相关组件
from binance import Client, ThreadedWebsocketManager, ThreadedDepthCacheManager
from binance.exceptions import BinanceAPIException

# 初始化Binance客户端（需要填入你的API Key和Secret）
api_key = 'edzrwA30X4wd07aqwGqFq3zb1ydxp0FpAapQEVyF05jnwgZGrWMiD113Ze21xEJv'
api_secret = 'CYhudmj2oIIDcE8nG6i2QfqY6RYTLbQ9p8YSwdw28wqgnVSnBFWjcnwnGDM9cStm'
client = Client(api_key, api_secret)

market_depth_tool_info = {
    "type": "function",
    "function": {
        "name": "get_market_depth",
        "description": "当你需要获取某个交易对的市场深度时，请调用此函数。",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "交易对名称",
                }
            }
        }
    }
}
def get_market_depth(symbol='BTCUSDT'):
    # 获取BTCUSDT交易对的市场深度（订单簿）
    depth = client.get_order_book(symbol=symbol)
    return depth

# 创建一个测试市价买单（不会真正成交，仅用于测试）
# order = client.create_test_order(
#     symbol='BTCUSDT',
#     side=Client.SIDE_BUY,
#     type=Client.ORDER_TYPE_MARKET,
#     quantity=100)
# print("创建测试订单成功")

# 获取所有交易对的最新价格
# prices = client.get_all_tickers()
# print("所有交易对价格:", prices)
#
# # 获取历史K线数据（1分钟K线，最近一天）
# klines = client.get_historical_klines("BTCUSDT", Client.KLINE_INTERVAL_1MINUTE, "1 day ago UTC")
# print("BTCUSDT最近一天的1分钟K线数据:", klines[:2])  # 只打印前两条数据
#
# # 获取历史K线数据（30分钟K线，2017年12月）
# klines = client.get_historical_klines("BTCUSDT", Client.KLINE_INTERVAL_30MINUTE, "1 Dec, 2017", "1 Jan, 2018")
# print("BTCUSDT 2017年12月的30分钟K线数据:", klines[:2])  # 只打印前两条数据
#
# # 获取历史K线数据（周K线，自2017年1月起）
# klines = client.get_historical_klines("BTCUSDT", Client.KLINE_INTERVAL_1WEEK, "1 Jan, 2017")
# print("BTCUSDT 自2017年以来的周K线数据:", klines[:2])  # 只打印前两条数据
historical_klines_tool_info = {
    "type": "function",
    "function": {
        "name": "get_historical_klines",
        "description": "当你想知道某个symbol的历史K线数据时，请调用此函数。",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "交易对名称，如BNBBTC",
                },
                "interval": {
                    "type": "string",
                    "description": "K线间隔，如1m、5m、15m、30m、1h、1d等",
                },
                "start_str": {
                    "type": "string",
                    "description": "开始时间，格式为YYYY-MM-DD HH:mm:ss"
                },
                "end_str": {
                    "type": "string",
                    "description": "结束时间，格式为YYYY-MM-DD HH:mm:ss"
                }
            },
            "required": ["symbol", "interval", "start_str","end_str"]
        }
    }
}
def get_historical_klines(symbol, interval, start_str, end_str=None):
    """获取历史K线数据"""
    return client.get_historical_klines(symbol, interval, start_str, end_str)

tickers_tool_info = {
    "type": "function",
    "function": {
        "name": "get_tickers",
        "description": "当你想知道某个交易对的最新价格，请调用此函数。",
        "parameters": {
            # symbol, interval, start_str, end_str
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "交易对名称，BTCUSDT，为空则获取全部的。",
                }
            }
        }
    }
}
def get_tickers(symbol = 'BTCUSDT'):
    """
    获取所有交易对最新价格
    [{'symbol': 'MATICBTC', 'price': '0.00000667'}]
    """
    prices = client.get_all_tickers()
    if symbol is None or symbol == '':
        return  prices
    # 筛选出指定交易对的最新价格
    return [price for price in prices if price['symbol'] == symbol]
