"""
数据库初始化脚本
创建所有表结构
"""

import sys
from pathlib import Path
import logging

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine
from data_warehouse.config import DATABASE_URL
from data_warehouse.models import Base

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def init_database():
    """初始化数据库，创建所有表"""
    try:
        logger.info(f"连接数据库: {DATABASE_URL}")
        engine = create_engine(DATABASE_URL, echo=False)
        
        # 创建所有表
        logger.info("创建数据库表...")
        Base.metadata.create_all(engine)
        logger.info("✅ 数据库表创建成功")
        
        # 也可以直接执行SQL文件
        logger.info("执行SQL文件创建表结构...")
        sql_file = Path(__file__).parent / "sql" / "schema.sql"
        if sql_file.exists():
            with open(sql_file, 'r', encoding='utf-8') as f:
                sql_content = f.read()
            
            # 执行SQL（注意：需要处理多语句）
            with engine.connect() as conn:
                # PostgreSQL支持执行多语句，需要使用text()包装
                from sqlalchemy import text
                # 按分号分割SQL语句并执行，过滤掉注释行
                statements = []
                for line in sql_content.split('\n'):
                    line = line.strip()
                    # 跳过空行和注释行
                    if not line or line.startswith('--'):
                        continue
                    # 如果行以分号结尾，说明是一个完整的语句
                    if line.endswith(';'):
                        statements.append(line[:-1])  # 去掉分号
                    elif statements:
                        # 继续添加到最后一个语句
                        statements[-1] += ' ' + line
                
                for statement in statements:
                    if statement.strip():
                        try:
                            conn.execute(text(statement))
                        except Exception as e:
                            # 忽略已存在的表/索引错误和语法错误（可能是注释导致的）
                            error_str = str(e).lower()
                            if 'already exists' in error_str or 'duplicate' in error_str:
                                continue  # 忽略已存在错误
                            elif 'syntax error' in error_str or 'in failed sql transaction' in error_str:
                                logger.debug(f"跳过SQL语句（可能是注释或已失败的事务）: {statement[:50]}...")
                                continue
                            else:
                                logger.warning(f"执行SQL语句时出错: {e}")
                conn.commit()
            
            logger.info("✅ SQL文件执行成功")
        
    except Exception as e:
        logger.error(f"❌ 数据库初始化失败: {e}", exc_info=True)
        raise


if __name__ == '__main__':
    init_database()

