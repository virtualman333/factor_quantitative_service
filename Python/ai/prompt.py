# 回测专用提示词
from Python.ai.AIUtil import call_with_messages


def call_ai_back_trade(datetime):
    ai_prompt = f"""
            假设 现在是{datetime}，你只能分析{datetime}之前6小时的数据，请给出你的交易建议。
            1、调用get_flash_entries，获取最新新闻资讯，时间为{datetime}最近6小时内的新闻资讯。
            2、比特币历史K线数据，时间为{datetime}最近30天的数据，interval为1d。
            你是一个资深的虚拟货币（BTCUSDT）交易大师，你要根据当前的新闻资讯、比特币历史K线数据、当前持仓信息、市场深度等指标，进行分析。如果你不知道数据，请调用tool_call中提供的接口获取，不要自己创造数据。
            请执行激进的交易策略，请尽可能避免观望。
            请严格按照JSON格式返回交易建议，包含以下字段：
            - action: 操作建议，必须是'买入'、'卖出'或'观望'中的一个
            - volume: 建议的交易数量
            - price: 建议的交易价格，可以是具体数值或'市价'
            - reason: 给出建议的详细理由
            注意：调用的接口时间范围不能大于6小时。
            请注意只返回JSON格式的内容，不要添加任何额外的解释或说明文字。
            """
    try:
        # 调用AI获取决策
        response = call_with_messages(ai_prompt)

        import re
        import json
        # 提取JSON部分
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            decision = json.loads(json_str)
            return decision
        else:
            raise ValueError("无法从AI响应中提取JSON")

    except Exception as e:
        print(f"从AI获取决策时出错: {e}")
        # 返回默认决策
        return {
            "action": "观望",
            "money": 0,
            "price": "市价",
            "reason": f"AI分析失败: {str(e)}"
        }