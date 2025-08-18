from binance import Client, ThreadedWebsocketManager, ThreadedDepthCacheManager
import time
import logging

# 初始化Binance客户端（需要填入你的API Key和Secret）
api_key = 'edzrwA30X4wd07aqwGqFq3zb1ydxp0FpAapQEVyFQ5jnwgZGrWMiD113Ze21xEJv'
api_secret = 'CYhudmj2oIIDcE8nG6i2QfqY6RYTLbQ9p8YSwdw28wqgnVSnBFWjcnwnGDM9cStm'
client = Client(api_key, api_secret)

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FundingRateArbitrage:
    def __init__(self, client, symbol, amount):
        """
        初始化资金费率套利策略
        :param client: Binance客户端
        :param symbol: 交易对，如BTCUSDT
        :param amount: 交易数量
        """
        self.client = client
        self.symbol = symbol
        self.amount = amount
        self.pair = symbol.replace('USDT', '')  # 例如: BTCUSDT -> BTC
        
    def get_funding_rate(self, symbol):
        """
        获取永续合约资金费率
        :param symbol: 合约交易对
        :return: 资金费率
        """
        try:
            funding_rate_info = self.client.futures_funding_rate(symbol=symbol, limit=1)
            print(symbol + '的永续合约资金费率为:' + (funding_rate_info[0]['fundingRate']))
            return float(funding_rate_info[0]['fundingRate'])
        except Exception as e:
            logger.error(f"获取资金费率失败: {e}")
            return None
    
    def get_high_funding_rate_symbols(self, threshold=0.001):
        """
        获取高资金费率的合约交易对
        :param threshold: 资金费率阈值
        :return: 高资金费率交易对列表
        """
        try:
            exchange_info = self.client.futures_exchange_info()
            high_rate_symbols = []
            
            for symbol_info in exchange_info['symbols']:
                symbol = symbol_info['symbol']
                if symbol.endswith('USDT') and symbol_info['status'] == 'TRADING':
                    funding_rate = self.get_funding_rate(symbol)
                    if funding_rate and funding_rate > threshold:
                        print('高资金费率交易对为:' + symbol)
                        high_rate_symbols.append({
                            'symbol': symbol,
                            'fundingRate': funding_rate
                        })
            return sorted(high_rate_symbols, key=lambda x: x['fundingRate'], reverse=True)
        except Exception as e:
            logger.error(f"获取高资金费率交易对失败: {e}")
            return []
    
    def get_spot_balance(self, asset):
        """
        获取现货账户余额
        :param asset: 资产名称
        :return: 可用余额
        """
        try:
            account_info = self.client.get_account()
            for balance in account_info['balances']:
                if balance['asset'] == asset:
                    print('现货余额为:' + (balance['free']))
                    return float(balance['free'])
            return 0.0
        except Exception as e:
            logger.error(f"获取现货余额失败: {e}")
            return 0.0
    
    def get_futures_balance(self):
        """
        获取期货账户USDT余额
        :return: USDT余额
        """
        try:
            account_info = self.client.futures_account()
            for asset in account_info['assets']:
                if asset['asset'] == 'USDT':
                    print('期货USDT余额为:' + (asset['walletBalance']))
                    return float(asset['availableBalance'])
            return 0.0
        except Exception as e:
            logger.error(f"获取期货账户余额失败: {e}")
            return 0.0
    
    def place_spot_buy_order(self, symbol, quantity):
        """
        下现货买入订单
        :param symbol: 交易对
        :param quantity: 数量
        :return: 订单结果
        """
        try:
            order = self.client.order_market_buy(
                symbol=symbol,
                quantity=quantity
            )
            print(f"现货买入订单执行成功: {order}")
            return order
        except Exception as e:
            logger.error(f"现货买入订单执行失败: {e}")
            return None
    
    def place_futures_short_order(self, symbol, quantity):
        """
        下期货做空订单
        :param symbol: 合约交易对
        :param quantity: 数量
        :return: 订单结果
        """
        try:
            order = self.client.futures_create_order(
                symbol=symbol,
                side='SELL',
                type='MARKET',
                quantity=quantity
            )
            print(f"期货做空订单执行成功: {order}")
            return order
        except Exception as e:
            logger.error(f"期货做空订单执行失败: {e}")
            return None
    
    def close_spot_position(self, symbol, quantity):
        """
        平仓现货头寸（卖出）
        :param symbol: 交易对
        :param quantity: 数量
        :return: 订单结果
        """
        try:
            order = self.client.order_market_sell(
                symbol=symbol,
                quantity=quantity
            )
            print(f"现货卖出订单执行成功: {order}")
            return order
        except Exception as e:
            logger.error(f"现货卖出订单执行失败: {e}")
            return None
    
    def close_futures_position(self, symbol, quantity):
        """
        平仓期货头寸（买入平空）
        :param symbol: 合约交易对
        :param quantity: 数量
        :return: 订单结果
        """
        try:
            order = self.client.futures_create_order(
                symbol=symbol,
                side='BUY',
                type='MARKET',
                quantity=quantity,
                reduceOnly=True
            )
            print(f"期货买入平空订单执行成功: {order}")
            return order
        except Exception as e:
            logger.error(f"期货买入平空订单执行失败: {e}")
            return None
    
    def execute_arbitrage_strategy(self):
        """
        执行资金费率套利策略
        """
        # 获取高资金费率交易对
        high_rate_symbols = self.get_high_funding_rate_symbols()
        
        if not high_rate_symbols:
            print("当前没有找到高资金费率的交易对")
            return
        
        # 选择资金费率最高的交易对
        target_symbol = high_rate_symbols[0]['symbol']
        funding_rate = high_rate_symbols[0]['fundingRate']
        spot_symbol = target_symbol  # 现货交易对名与合约相同
        
        print(f"选择交易对: {target_symbol}, 资金费率: {funding_rate:.4f}")
        
        # 检查账户余额
        asset_name = target_symbol.replace('USDT', '')
        spot_balance = self.get_spot_balance(asset_name)
        futures_balance = self.get_futures_balance()
        
        print(f"现货{asset_name}余额: {spot_balance}")
        print(f"期货USDT余额: {futures_balance}")
        
        # 计算交易数量（简化处理，实际应考虑精度等）
        quantity = self.amount
        
        # 执行套利: 现货做多 + 合约做空
        print("开始执行资金费率套利策略...")
        
        # 下现货买入订单
        spot_order = self.place_spot_buy_order(spot_symbol, quantity)
        if not spot_order:
            logger.error("现货买入订单执行失败，取消策略执行")
            return
        
        # 下期货做空订单
        futures_order = self.place_futures_short_order(target_symbol, quantity)
        if not futures_order:
            logger.error("期货做空订单执行失败，尝试平仓现货...")
            self.close_spot_position(spot_symbol, quantity)
            return
        
        print(f"套利策略执行完成: 现货买入{quantity} {asset_name}, 合约做空{quantity} {asset_name}")
        print(f"等待资金费率结算获取收益，当前资金费率: {funding_rate:.4f}")
        
        # 这里可以添加定时检查和策略平仓逻辑
        # 为简化示例，我们不自动平仓，实际使用时应添加风险管理逻辑

# 使用示例
if __name__ == "__main__":
    # 创建套利策略实例
    # 参数：客户端对象，交易对，交易数量
    arbitrage = FundingRateArbitrage(client, "BTCUSDT", 0.001)
    # arbitrage.get_funding_rate("BTCUSDT")
    # 执行套利策略
    arbitrage.execute_arbitrage_strategy()