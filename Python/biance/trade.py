# 基于AI的交易系统实现
import json
import time
from datetime import datetime
import os
import sys

# 添加项目根目录到Python路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

# 导入必要的模块
from Python.ai.AIUtil import call_with_messages
from Python.biance.main import client, get_historical_klines, get_tickers, get_market_depth

class AITradingSystem:
    """基于AI的交易系统，用于根据AI分析结果执行买入卖出操作"""
    
    def __init__(self, symbol='BTCUSDT', initial_balance=10000, use_test_order=True):
        """初始化交易系统
        
        Args:
            symbol: 交易对，默认为'BTCUSDT'
            initial_balance: 初始资金，默认为10000
            use_test_order: 是否使用测试订单，默认为True
        """
        self.symbol = symbol
        self.initial_balance = initial_balance
        self.use_test_order = use_test_order
        self.trade_history = []
        self.last_trade_time = 0
        self.trade_interval = 3600  # 交易间隔，单位：秒
        self.min_kline_period = '15m'  # 最小K线周期
        self.max_kline_period = '1d'  # 最大K线周期
        self.lookback_days = 7  # 历史数据回溯天数
        
    def get_market_data(self):
        """获取市场数据，包括K线数据、最新价格和市场深度"""
        try:
            # 获取当前时间和历史时间
            now = datetime.now()
            end_time = now.strftime('%Y-%m-%d %H:%M:%S')
            start_time = (now.replace(hour=0, minute=0, second=0, microsecond=0) -
                         timedelta(days=self.lookback_days)).strftime('%Y-%m-%d %H:%M:%S')
            
            # 获取历史K线数据
            klines_15m = get_historical_klines(self.symbol, self.min_kline_period, start_time, end_time)
            klines_1d = get_historical_klines(self.symbol, self.max_kline_period, start_time, end_time)
            
            # 获取最新价格
            ticker = get_tickers(self.symbol)
            current_price = float(ticker[0]['price']) if ticker else 0
            
            # 获取市场深度
            market_depth = get_market_depth(self.symbol)
            
            return {
                'klines_15m': klines_15m,
                'klines_1d': klines_1d,
                'current_price': current_price,
                'market_depth': market_depth,
                'timestamp': now
            }
        except Exception as e:
            print(f"获取市场数据时出错: {e}")
            return None
    
    def get_account_balance(self):
        """获取账户余额信息"""
        try:
            # 获取账户资产信息
            account = client.get_account()
            balances = account['balances']
            
            # 返回账户余额信息
            return {
                'balances': balances,
                'total_asset': float(account.get('totalAssetOfBtc', 0))
            }
        except Exception as e:
            print(f"获取账户余额时出错: {e}")
            return None
    
    def analyze_market_with_ai(self, market_data):
        """使用AI分析市场并获取交易建议"""
        if not market_data:
            return None
        
        try:
            # 获取账户余额信息
            account_balance = self.get_account_balance()
            
            # 准备发送给AI的提示信息
            prompt = f"""
            你是一个资深的虚拟货币交易大师，请根据以下{self.symbol}的市场数据进行分析：
            
            # 当前市场数据
            - 当前价格: {market_data['current_price']}
            - 时间: {market_data['timestamp']}
            
            # 市场深度信息
            - 买单深度(前5档): {market_data['market_depth']['bids'][:5]}
            - 卖单深度(前5档): {market_data['market_depth']['asks'][:5]}
            
            # 账户信息
            {f'- 账户余额信息: {account_balance}' if account_balance else '- 无法获取账户余额信息'}
            
            # 历史K线数据
            - 最近{self.lookback_days}天的{self.min_kline_period}K线数据条数: {len(market_data['klines_15m'])}
            - 最近{self.lookback_days}天的{self.max_kline_period}K线数据条数: {len(market_data['klines_1d'])}
            
            请严格按照JSON格式返回交易建议，包含以下字段：
            - action: 操作建议，必须是'买入'、'卖出'或'观望'中的一个
            - volume: 建议的交易数量
            - price: 建议的交易价格，可以是具体数值或'市价'
            - reason: 给出建议的详细理由
            
            请注意只返回JSON格式的内容，不要添加任何额外的解释或说明文字。
            """
            
            # 调用AI模型获取交易建议
            response = call_with_messages(prompt)
            
            # 解析AI的回复
            try:
                # 提取JSON内容
                json_start = response.find('{')
                json_end = response.rfind('}') + 1
                if json_start != -1 and json_end != -1:
                    json_str = response[json_start:json_end]
                    advice = json.loads(json_str)
                    return advice
            except json.JSONDecodeError as e:
                print(f"解析AI回复的JSON格式错误: {e}")
                print(f"AI原始回复: {response}")
            except Exception as e:
                print(f"解析AI回复时发生未知错误: {e}")
            
            return None
        except Exception as e:
            print(f"调用AI模型分析市场时出错: {e}")
            return None
    
    def execute_trade(self, advice):
        """根据AI的建议执行交易"""
        if not advice:
            print("没有有效的交易建议，无法执行交易")
            return False
        
        # 检查是否达到交易间隔要求
        current_time = time.time()
        if current_time - self.last_trade_time < self.trade_interval:
            print(f"交易间隔不足，上次交易时间: {datetime.fromtimestamp(self.last_trade_time).strftime('%Y-%m-%d %H:%M:%S')}")
            return False
        
        try:
            action = advice.get('action', '观望').strip()
            volume = advice.get('volume', 0)
            price = advice.get('price', '市价')
            reason = advice.get('reason', '无')
            
            print(f"\n执行交易: {action}")
            print(f"- 交易数量: {volume}")
            print(f"- 交易价格: {price}")
            print(f"- 理由: {reason}")
            
            # 确保volume是有效的数值
            try:
                volume = float(volume)
                if volume <= 0:
                    print("无效的交易数量")
                    return False
            except (ValueError, TypeError):
                print(f"无效的交易数量值: {volume}")
                return False
            
            # 执行买入操作
            if action == '买入':
                if self.use_test_order:
                    # 使用测试订单
                    order = client.create_test_order(
                        symbol=self.symbol,
                        side='BUY',
                        type='MARKET' if price == '市价' else 'LIMIT',
                        quantity=volume,
                        price=price if price != '市价' else None
                    )
                else:
                    # 执行真实买入订单
                    order = client.create_order(
                        symbol=self.symbol,
                        side='BUY',
                        type='MARKET' if price == '市价' else 'LIMIT',
                        quantity=volume,
                        price=price if price != '市价' else None
                    )
                
            # 执行卖出操作
            elif action == '卖出':
                if self.use_test_order:
                    # 使用测试订单
                    order = client.create_test_order(
                        symbol=self.symbol,
                        side='SELL',
                        type='MARKET' if price == '市价' else 'LIMIT',
                        quantity=volume,
                        price=price if price != '市价' else None
                    )
                else:
                    # 执行真实卖出订单
                    order = client.create_order(
                        symbol=self.symbol,
                        side='SELL',
                        type='MARKET' if price == '市价' else 'LIMIT',
                        quantity=volume,
                        price=price if price != '市价' else None
                    )
            
            # 观望操作
            elif action == '观望':
                print("执行观望策略，不进行交易")
                return True
            
            else:
                print(f"未知的操作建议: {action}")
                return False
            
            # 记录交易历史
            trade_record = {
                'timestamp': current_time,
                'datetime': datetime.fromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S'),
                'action': action,
                'volume': volume,
                'price': price,
                'reason': reason,
                'order': order if not self.use_test_order else '测试订单',
                'is_test': self.use_test_order
            }
            
            self.trade_history.append(trade_record)
            self.last_trade_time = current_time
            
            print(f"交易执行成功: {trade_record}")
            return True
            
        except Exception as e:
            print(f"执行交易时出错: {e}")
            return False
    
    def run_trading_bot(self):
        """运行交易机器人，持续分析市场并执行交易"""
        print(f"开始运行基于AI的交易机器人 - 交易对: {self.symbol}")
        print(f"使用测试订单: {self.use_test_order}")
        print(f"交易间隔: {self.trade_interval}秒")
        
        try:
            while True:
                print(f"\n{'-'*50}")
                print(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                
                # 获取市场数据
                print("正在获取市场数据...")
                market_data = self.get_market_data()
                if not market_data:
                    print("获取市场数据失败，等待下次循环")
                    time.sleep(60)
                    continue
                
                # 使用AI分析市场
                print("正在使用AI分析市场...")
                advice = self.analyze_market_with_ai(market_data)
                if not advice:
                    print("获取AI交易建议失败，等待下次循环")
                    time.sleep(60)
                    continue
                
                # 根据AI建议执行交易
                self.execute_trade(advice)
                
                # 等待下一次交易循环
                print(f"等待{self.trade_interval}秒后进行下一次分析")
                time.sleep(self.trade_interval)
                
        except KeyboardInterrupt:
            print("交易机器人已手动停止")
        except Exception as e:
            print(f"交易机器人运行出错: {e}")
        
        # 打印交易历史
        print("\n交易历史记录:")
        for i, trade in enumerate(self.trade_history, 1):
            print(f"交易 {i}: {trade['datetime']} - {trade['action']} {trade['volume']} {self.symbol} @ {trade['price']}")
        
    def run_one_time_trade(self):
        """执行单次交易分析和操作"""
        print(f"执行单次交易分析 - 交易对: {self.symbol}")
        
        # 获取市场数据
        print("正在获取市场数据...")
        market_data = self.get_market_data()
        if not market_data:
            print("获取市场数据失败")
            return False
        
        # 使用AI分析市场
        print("正在使用AI分析市场...")
        advice = self.analyze_market_with_ai(market_data)
        if not advice:
            print("获取AI交易建议失败")
            return False
        
        # 根据AI建议执行交易
        return self.execute_trade(advice)


# 测试代码
if __name__ == "__main__":
    # 创建交易系统实例，使用测试订单
    trading_system = AITradingSystem(symbol='BTCUSDT', use_test_order=True)
    
    # 可以选择运行单次交易或连续交易机器人
    # 执行单次交易分析
    trading_system.run_one_time_trade()
    
    # 或者运行连续交易机器人
    # trading_system.run_trading_bot()
    
    print("交易分析完成")