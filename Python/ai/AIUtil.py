from openai import OpenAI
from datetime import datetime, timedelta, date
import json
import os
import random

from Python.biance.main import historical_klines_tool_info, get_historical_klines, tickers_tool_info, \
    market_depth_tool_info, get_market_depth, get_tickers
from Python.flash.main import get_flash_entries, toolInfo as flashToolInfo

client = OpenAI(
    # 若没有配置环境变量，请用百炼API Key将下行替换为：api_key="sk-xxx",
    api_key="sk-9adb75816826497ca74371c057626483",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",  # 填写DashScope SDK的base_url
)
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(obj, date):
            return obj.strftime('%Y-%m-%d')
        return super().default(obj)


# 定义工具列表，模型在选择使用哪个工具时会参考工具的name和description
tools = [
    # 工具1 获取当前时刻的时间
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "get_current_time",
    #         "description": "当你想知道现在的时间时非常有用。",
    #         # 因为获取当前时间无需输入参数，因此parameters为空字典
    #         "parameters": {},
    #     },
    # },
    # 工具2 获取指定时间的新闻资讯
    flashToolInfo,
    # 获取历史K线数据
    historical_klines_tool_info,
    # 获取交易对最新价格
    # tickers_tool_info,
    # 获取市场深度
    # market_depth_tool_info
]
# 检查tools列表
print(tools)

# 查询当前时间的工具。返回结果示例：“当前时间：2024-04-15 17:15:18。“
def get_current_time():
    # 获取当前日期和时间 -1天
    current_datetime = (datetime.now() - timedelta(days=1))
    # current_datetime = datetime.now()
    # 格式化当前日期和时间
    formatted_time = current_datetime.strftime("%Y-%m-%d %H:%M:%S")
    # 返回格式化后的当前时间
    return f"当前时间：{formatted_time}。"


# 封装模型响应函数
def get_response(messages):
    completion = client.chat.completions.create(
        model="qwen-flash",  # 模型列表：https://help.aliyun.com/zh/model-studio/getting-started/models
        messages=messages,
        tools=tools,
    )
    return completion


def call_with_messages(content):
    print("\n")
    messages = [
        {
            "content": content,
            "role": "user",
        }
    ]
    print("-" * 60)
    # 模型的第一轮调用
    i = 1
    first_response = get_response(messages)
    assistant_output = first_response.choices[0].message
    print(f"\n第{i}轮大模型输出信息：{first_response}\n")
    if assistant_output.content is None:
        assistant_output.content = ""
    messages.append(assistant_output)
    # 如果不需要调用工具，则直接返回最终答案
    if (
            assistant_output.tool_calls is None
    ):  # 如果模型判断无需调用工具，则将assistant的回复直接打印出来，无需进行模型的第二轮调用
        print(f"无需调用工具，我可以直接回复：{assistant_output.content}")
        return assistant_output.content
    # 如果需要调用工具，则进行模型的多轮调用，直到模型判断无需调用工具
    while assistant_output.tool_calls is not None:
        tool_info = {
            "content": "",
            "role": "tool",
            "tool_call_id": assistant_output.tool_calls[0].id,
        }
        tool_name = assistant_output.tool_calls[0].function.name
        arguments = assistant_output.tool_calls[0].function.arguments
        # 调用tool_name的函数
        if tool_name == "get_historical_klines":
            # 获取历史K线数据
            arguments_object = json.loads(arguments)
            symbol = arguments_object['symbol']
            interval = arguments_object['interval']
            start_str = arguments_object['start_str']
            end_str = arguments_object['end_str']
            tool_info["content"] = get_historical_klines(symbol, interval, start_str, end_str)
        elif tool_name == "get_flash_entries":
            # 获取指定时间段内的快讯
            arguments_object = json.loads(arguments)
            print(arguments_object)
            start_time = arguments_object['start_time']
            end_time = arguments_object['end_time']
            tool_info["content"] = get_flash_entries(start_time, end_time)
        elif tool_name== "get_current_time":
            # 运行查询时间工具
            tool_info["content"] = get_current_time()
        elif tool_name == "get_tickers":
            # 获取交易对最新价格
            arguments_object = json.loads(arguments)
            symbol = arguments_object['symbol']
            tool_info["content"] = get_tickers(symbol)
        elif tool_name == "get_market_depth":
            # 获取市场深度
            arguments_object = json.loads(arguments)
            symbol = arguments_object['symbol']
            tool_info["content"] = get_market_depth(symbol)

        # 在 call_with_messages 函数中，处理 tool_output 时
        tool_info["content"] = json.dumps(tool_info["content"], cls=DateTimeEncoder, ensure_ascii=False)
        tool_output = tool_info["content"]
        print(f"工具输出信息：{tool_output}\n")
        print("-" * 60)
        messages.append(tool_info)
        assistant_output = get_response(messages).choices[0].message
        if assistant_output.content is None:
            assistant_output.content = ""
        messages.append(assistant_output)
        i += 1
        print(f"第{i}轮大模型输出信息：{assistant_output}\n")
    print(f"最终答案：{assistant_output.content}")
    return assistant_output.content


if __name__ == "__main__":
    call_with_messages("""
    你是一个资深的虚拟货币（BTCUSDT）交易大师，你要根据当前的新闻资讯、比特币历史K线数据、当前持仓信息、市场深度等指标，进行分析。如果你不知道数据，请调用tool_call中提供的接口获取，不要自己创造数据。
    请作出合理的交易动作
    请严格按照JSON格式返回交易建议，包含以下字段：
            - action: 操作建议，必须是'买入'、'卖出'或'观望'中的一个
            - volume: 建议的交易数量
            - price: 建议的交易价格，可以是具体数值或'市价'
            - reason: 给出建议的详细理由
            
    请注意只返回JSON格式的内容，不要添加任何额外的解释或说明文字。
    """)