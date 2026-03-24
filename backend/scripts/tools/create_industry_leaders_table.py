#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建行业龙头数据表
如果表已存在，则跳过
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).resolve().parent.parent.parent.parent
if not (project_root / 'data_warehouse').exists():
    project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def create_table():
    """创建 dim_industry_leader 表"""
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        # 检查表是否存在
        check_table_query = text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'dim_industry_leader'
            );
        """)
        table_exists = session.execute(check_table_query).scalar()
        
        if table_exists:
            logger.info("✅ 表 dim_industry_leader 已存在，跳过创建")
            return True
        
        # 读取SQL文件
        sql_file = project_root / 'migrations' / 'create_industry_leaders_table.sql'
        if not sql_file.exists():
            logger.error(f"❌ SQL文件不存在: {sql_file}")
            return False
        
        logger.info(f"📄 读取SQL文件: {sql_file}")
        with open(sql_file, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        # 按语句类型分组执行：先创建表，再创建索引，最后添加注释
        # 这样可以避免在表不存在时创建索引导致的错误
        
        # 1. 提取CREATE TABLE语句
        create_table_match = None
        import re
        create_table_pattern = r'CREATE TABLE[^;]+;'
        matches = re.finditer(create_table_pattern, sql_content, re.IGNORECASE | re.DOTALL)
        for match in matches:
            create_table_match = match.group(0)
            break
        
        if create_table_match:
            try:
                logger.info("📝 执行 CREATE TABLE 语句...")
                session.execute(text(create_table_match))
                session.commit()
                logger.info("✅ CREATE TABLE 执行成功")
            except Exception as e:
                error_msg = str(e).lower()
                if 'already exists' in error_msg:
                    logger.info("ℹ️  表已存在，跳过创建")
                else:
                    logger.error(f"❌ CREATE TABLE 执行失败: {e}")
                    session.rollback()
                    return False
        
        # 2. 提取并执行CREATE INDEX语句
        create_index_pattern = r'CREATE INDEX[^;]+;'
        index_statements = re.findall(create_index_pattern, sql_content, re.IGNORECASE | re.DOTALL)
        
        for idx, stmt in enumerate(index_statements, 1):
            try:
                logger.debug(f"📝 执行 CREATE INDEX {idx}/{len(index_statements)}...")
                session.execute(text(stmt))
            except Exception as e:
                error_msg = str(e).lower()
                if 'already exists' in error_msg:
                    logger.debug(f"ℹ️  索引已存在，跳过")
                else:
                    logger.warning(f"⚠️  CREATE INDEX {idx} 执行失败: {e}")
        
        session.commit()
        
        # 3. 提取并执行COMMENT语句
        comment_pattern = r"COMMENT ON[^;]+;"
        comment_statements = re.findall(comment_pattern, sql_content, re.IGNORECASE | re.DOTALL)
        
        for idx, stmt in enumerate(comment_statements, 1):
            try:
                logger.debug(f"📝 执行 COMMENT {idx}/{len(comment_statements)}...")
                session.execute(text(stmt))
            except Exception as e:
                # COMMENT语句失败不影响表的使用，只记录警告
                logger.debug(f"⚠️  COMMENT {idx} 执行失败（可忽略）: {e}")
        
        session.commit()
        
        # 4. 最终检查表是否存在
        table_exists_after = session.execute(check_table_query).scalar()
        if table_exists_after:
            logger.info("✅ 表 dim_industry_leader 创建成功！")
            return True
        else:
            logger.error("❌ 表创建后仍然不存在，请检查SQL文件")
            return False
        
    except Exception as e:
        session.rollback()
        logger.error(f"❌ 创建表失败: {e}", exc_info=True)
        return False
    finally:
        session.close()


if __name__ == "__main__":
    logger.info("="*60)
    logger.info("创建行业龙头数据表")
    logger.info("="*60)
    
    success = create_table()
    
    if success:
        logger.info("\n✅ 完成！现在可以使用 auto_fetch_industry_leaders.py 导入数据了")
    else:
        logger.error("\n❌ 失败！请检查错误信息")
        sys.exit(1)
