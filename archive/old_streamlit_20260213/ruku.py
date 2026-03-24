# -*- coding: utf-8 -*-
import pandas as pd
import sqlite3

# 1. 读取Excel数据
df = pd.read_excel('data.xlsx',sheet_name="ztfx11")
df.columns = df.columns.str.strip()

# 2. 连接SQLite数据库
conn = sqlite3.connect('honghuo_stock.db')
cursor = conn.cursor()

# 3. 创建表（如未创建）
create_table_sql = """
CREATE TABLE IF NOT EXISTS stock_info (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    name TEXT,
    price REAL,
    change_percent TEXT,
    change_amount REAL,
    turnover_percent TEXT,
    turnover_amount TEXT,
    volume TEXT,
    analysis TEXT,
    limit_up_date TEXT
)
"""
cursor.execute(create_table_sql)

# 4. 插入数据
insert_sql = """
INSERT INTO stock_info (code, name, price, change_percent, change_amount, turnover_percent, turnover_amount, volume, analysis, limit_up_date)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

def safe_float(val):
    try:
        return float(val)
    except (ValueError, TypeError):
        return None

for _, row in df.iterrows():
    cursor.execute(insert_sql, (
        str(row['代码']),
        row['名称'],
        safe_float(row['价格']),
        str(row['涨幅']),
        safe_float(row['涨跌']),
        str(row['换手']),
        str(row['成交额']),
        str(row['成交量']),
        str(row['涨停分析']),
        pd.to_datetime(row['涨停日期']).strftime('%Y-%m-%d')
    ))

conn.commit()
cursor.close()
conn.close()
print("数据已成功导入SQLite数据库！")
