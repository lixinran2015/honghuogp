"""
从数据库反射生成 SQLAlchemy 模型
"""
import os
import sys

# 添加项目路径
sys.path.insert(0, '/Users/lxr/workspace/honghuogp')

from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import declarative_base
from data_warehouse.config import DATABASE_URL

# 创建引擎
engine = create_engine(DATABASE_URL)
metadata = MetaData()
Base = declarative_base()

# 反射所有表
metadata.reflect(bind=engine)

# 生成模型代码
output = []
output.append("from typing import Optional")
output.append("import datetime")
output.append("import decimal")
output.append("")
output.append("from sqlalchemy import ARRAY, BigInteger, Boolean, Column, Date, DateTime, Double, ForeignKeyConstraint, Index, Integer, JSON, Numeric, PrimaryKeyConstraint, String, Table, Text, Time, UniqueConstraint, text")
output.append("from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship")
output.append("")
output.append("")
output.append("class Base(DeclarativeBase):")
output.append("    pass")
output.append("")

# 生成表类
for table_name in sorted(metadata.tables.keys()):
    table = metadata.tables[table_name]

    # 跳过非 fact/dim/raw 开头的表（可选）
    if not any(table_name.startswith(prefix) for prefix in ['fact_', 'dim_', 'raw_', 'etl_', 'temp_', 't_']):
        continue

    class_name = ''.join(word.capitalize() for word in table_name.split('_'))
    if table_name.startswith('t_'):
        # Table 对象
        output.append(f"")
        output.append(f"t_{table_name[2:]} = Table(")
        output.append(f"    '{table_name}', Base.metadata,")
        # 列
        for col in table.columns:
            col_type = str(col.type)
            if 'VARCHAR' in col_type:
                col_type = f"String({col.type.length})"
            elif 'INTEGER' in col_type:
                col_type = "Integer"
            elif 'BIGINT' in col_type:
                col_type = "BigInteger"
            elif 'NUMERIC' in col_type or 'DECIMAL' in col_type:
                col_type = f"Numeric({col.type.precision}, {col.type.scale})"
            elif 'TIMESTAMP' in col_type:
                col_type = "DateTime"
            elif 'DATE' in col_type:
                col_type = "Date"
            elif 'BOOLEAN' in col_type:
                col_type = "Boolean"
            elif 'DOUBLE' in col_type or 'REAL' in col_type or 'FLOAT' in col_type:
                col_type = "Double(53)"
            elif 'JSON' in col_type:
                col_type = "JSON"
            elif 'TEXT' in col_type:
                col_type = "Text"
            else:
                col_type = f"String(255)  # {col_type}"

            nullable = "" if col.nullable else ", nullable=False"
            server_default = f", server_default=text('{col.server_default.arg}')" if col.server_default else ""
            comment = f", comment='{col.comment}'" if col.comment else ""
            output.append(f"    Column('{col.name}', {col_type}{nullable}{server_default}{comment}),")
        output.append(")")
    else:
        # Class 对象
        output.append(f"")
        output.append(f"")
        output.append(f"class {class_name}(Base):")
        output.append(f"    __tablename__ = '{table_name}'")

        # 主键约束
        pk_cols = [col.name for col in table.primary_key.columns]
        if pk_cols:
            pk_str = ", ".join([f"'{c}'" for c in pk_cols])
            output.append(f"    __table_args__ = (")
            output.append(f"        PrimaryKeyConstraint({pk_str}),")
            output.append(f"    )")

        output.append("")

        # 列
        for col in table.columns:
            col_type = str(col.type)
            mapped_type = ""

            if 'VARCHAR' in col_type:
                mapped_type = f"String({col.type.length})"
            elif 'INTEGER' in col_type:
                mapped_type = "Integer"
            elif 'BIGINT' in col_type:
                mapped_type = "BigInteger"
            elif 'NUMERIC' in col_type or 'DECIMAL' in col_type:
                mapped_type = f"Numeric({col.type.precision}, {col.type.scale})"
            elif 'TIMESTAMP' in col_type:
                mapped_type = "DateTime"
            elif 'DATE' in col_type:
                mapped_type = "Date"
            elif 'BOOLEAN' in col_type:
                mapped_type = "Boolean"
            elif 'DOUBLE' in col_type or 'REAL' in col_type or 'FLOAT' in col_type:
                mapped_type = "Double(53)"
            elif 'JSON' in col_type:
                mapped_type = "JSON"
            elif 'TEXT' in col_type:
                mapped_type = "Text"
            elif 'ARRAY' in col_type or '[]' in col_type:
                mapped_type = "ARRAY(String())"
            else:
                mapped_type = f"String(255)"

            is_pk = col.name in pk_cols
            pk_str = ", primary_key=True" if is_pk else ""
            nullable_str = ", nullable=False" if not col.nullable and not is_pk else ""

            comment_str = f", comment='{col.comment}'" if col.comment else ""

            if col.server_default:
                default_str = f", server_default=text('{str(col.server_default.arg)}')"
            else:
                default_str = ""

            output.append(f"    {col.name}: Mapped[Optional[{_get_python_type(col.type)}]] = mapped_column({mapped_type}{pk_str}{nullable_str}{default_str}{comment_str})")

# 写入文件
with open('/Users/lxr/workspace/honghuogp/data_warehouse/models/generated_models_new.py', 'w') as f:
    f.write('\n'.join(output))

print("Model generated successfully!")

def _get_python_type(sql_type):
    type_str = str(sql_type).upper()
    if 'VARCHAR' in type_str or 'TEXT' in type_str or 'CHAR' in type_str:
        return "str"
    elif 'INTEGER' in type_str or 'BIGINT' in type_str or 'SMALLINT' in type_str:
        return "int"
    elif 'NUMERIC' in type_str or 'DECIMAL' in type_str:
        return "decimal.Decimal"
    elif 'TIMESTAMP' in type_str or 'DATETIME' in type_str:
        return "datetime.datetime"
    elif 'DATE' in type_str:
        return "datetime.date"
    elif 'BOOLEAN' in type_str or 'BOOL' in type_str:
        return "bool"
    elif 'DOUBLE' in type_str or 'REAL' in type_str or 'FLOAT' in type_str:
        return "float"
    elif 'JSON' in type_str:
        return "dict"
    elif 'ARRAY' in type_str or '[]' in type_str:
        return "list"
    else:
        return "str"
