import mysql.connector
from mysql.connector import Error

toolInfo = {
    "type": "function",
    "function": {
        "name": "get_flash_entries",
        "description": "当你想查询某个时间段的新闻资讯数据时，请调用改功能",
        "parameters": {
            "type": "object",
            "properties": {
                "start_time": {
                    "type": "string",
                    "description": "要查询资讯的开始时间，精确到秒，非时间戳，格式为：2025-08-13 22:57:41",
                },
                "end_time": {
                    "type": "string",
                    "description": "要查询资讯的结束时间，精确到秒,非时间戳，格式为：2025-08-13 22:57:41",
                }
            },
            "required": ["start_time","end_time"],
        },
    },
}

def get_flash_entries(start_time, end_time):
    print("正在获取 flash_entries 表中的数据...")
    """
    从 flash_entries 表中获取所有数据
    """
    connection = None
    cursor = None
    try:
        # 创建数据库连接
        connection = mysql.connector.connect(
            host='47.119.132.60',        # 数据库主机地址
            user='intelligenceAutoTrade',    # 用户名
            password='intelligenceAutoTrade', # 密码
            database='intelligenceautotrade',  # 数据库名
            ssl_disabled = True
        )
        print("MySQL连接已建立", connection.is_connected())
        if connection.is_connected():
            cursor = connection.cursor(dictionary=True)  # 返回字典格式结果

            # 执行查询
            query = "SELECT * FROM flash_entries"
            params = []

            # 添加时间筛选条件
            if start_time or end_time:
                query += " WHERE "
                conditions = []

                if start_time:
                    conditions.append("captured_at >= %s")  # 假设时间字段名为 created_time
                    params.append(start_time)

                if end_time:
                    conditions.append("captured_at <= %s")  # 假设时间字段名为 created_time
                    params.append(end_time)

                query += " AND ".join(conditions)
            query += " ORDER BY captured_at DESC"
            print("查询语句:", query)
            cursor.execute(query,params)
            # 获取所有记录
            records = cursor.fetchall()

            print(f"共获取到 {len(records)} 条记录")
            return records

    except Error as e:
        print(f"数据库操作出错: {e}")
        return []

    finally:
        # 关闭连接
        if connection and connection.is_connected():
            cursor.close()
            connection.close()
            print("MySQL连接已关闭")

# 调用函数
if __name__ == "__main__":
    flash_entries = get_flash_entries("2025-08-13 22:57:41","2025-08-14 09:04:03")
    for entry in flash_entries:
        print(entry)
