import pandas as pd
from datasets import load_dataset


def export_dataset_to_csv(dataset, output_path='crypto_data.csv'):
    """将Hugging Face数据集转换为PyBroker所需格式并导出为CSV"""
    try:
        # 将数据集转换为Pandas DataFrame
        if hasattr(dataset, 'to_pandas'):
            df = dataset.to_pandas()
        elif 'train' in dataset and hasattr(dataset['train'], 'to_pandas'):
            df = dataset['train'].to_pandas()
        else:
            print("警告：无法直接将数据集转换为DataFrame")
            return False
        
        # 打印原始列名以便调试
        print(f"原始数据集列名: {list(df.columns)}")
        
        # 确保包含PyBroker所需的所有列
        required_columns = ['symbol', 'date', 'open', 'high', 'low', 'close']
        
        # 检查并转换列名（处理大小写和可能的变体）
        column_mapping = {}
        for col in df.columns:
            lower_col = col.lower()
            if 'symbol' in lower_col:
                column_mapping[col] = 'symbol'
            elif 'date' in lower_col or 'time' in lower_col:
                column_mapping[col] = 'date'
            elif 'open' in lower_col:
                column_mapping[col] = 'open'
            elif 'high' in lower_col:
                column_mapping[col] = 'high'
            elif 'low' in lower_col:
                column_mapping[col] = 'low'
            elif 'close' in lower_col:
                column_mapping[col] = 'close'
            elif 'volume' in lower_col:
                column_mapping[col] = 'volume'
        
        # 重命名列
        df.rename(columns=column_mapping, inplace=True)
        
        # 检查重命名后是否有所有必需的列
        for col in required_columns:
            if col not in df.columns:
                print(f"警告：缺少必需的列 '{col}'，尝试从其他列推断或创建默认值")
                if col == 'symbol':
                    df[col] = 'BTCUSDT'  # 默认设置为BTCUSDT
                elif col in ['open', 'high', 'low', 'close'] and 'price' in df.columns:
                    df[col] = df['price']
                else:
                    # 对于其他缺失的列，使用合理的默认值
                    if col in ['open', 'high', 'low', 'close']:
                        # 使用close列或随机值作为默认价格
                        if 'close' in df.columns:
                            df[col] = df['close']
                        else:
                            df[col] = 40000 + (df.index * 100) % 10000
        
        # 确保日期列格式正确
        if 'date' in df.columns:
            try:
                # 尝试将日期列转换为datetime格式
                df['date'] = pd.to_datetime(df['date'])
                # 格式化为日期字符串
                df['date'] = df['date'].dt.strftime('%Y-%m-%d %h:%M:%s')
            except:
                print("无法解析日期列，创建默认日期序列")
                # 创建日期序列
                dates = pd.date_range(start='2023-01-01', periods=len(df), freq='D')
                df['date'] = dates.strftime('%Y-%m-%d')
        
        # 重新将date列转换为datetime类型用于筛选
        df['date'] = pd.to_datetime(df['date'])
        
        # 筛选每天只保留一条数据（取每天的第一条）
        # 创建日期列（只包含日期，不包含时间）
        df['only_date'] = df['date'].dt.date
        
        # 按日期分组，每组只保留第一行数据
        df = df.groupby('only_date').first().reset_index(drop=True)
        
        # 重新格式化日期列
        df['date'] = df['date'].dt.strftime('%Y-%m-%d')
        print(f"已筛选数据，每天只保留一条，共 {len(df)} 行数据")
        
        # 添加volume列（如果不存在）
        if 'volume' not in df.columns:
            df['volume'] = 10000  # 默认成交量
        
        # 再次检查所有必需的列是否都存在
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            print(f"错误：CSV文件仍然缺少以下必需的列: {missing_columns}")
            return False
        
        # 打印最终列名以便验证
        print(f"处理后的数据集列名: {list(df.columns)}")
        
        # 导出为CSV文件
        df.to_csv(output_path, index=False)
        print(f"数据集已成功导出到: {output_path}")
        return True
    except Exception as e:
        print(f"导出过程中出错: {e}")
        return False


if __name__ == "__main__":
    # 加载加密货币数据集
    print("正在加载Hugging Face数据集...")
    ds = load_dataset("WinkingFace/CryptoLM-Bitcoin-BTC-USDT")
    
    # 直接导出数据集为CSV
    print("正在导出数据集为CSV格式...")
    export_dataset_to_csv(ds, 'crypto_data_export.csv')