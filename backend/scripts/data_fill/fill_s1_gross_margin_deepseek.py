"""
使用Deepseek API为S1股票池补充毛利率和PE数据
直接向Deepseek API请求财务数据
"""

import sys
import logging
import json
import requests
from pathlib import Path
from datetime import date
from typing import Optional, Dict, List

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.services.data.postgres_warehouse import PostgresWarehouse
from data_warehouse.models import FactDailyFundamental
from sqlalchemy import text
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config():
    """加载配置文件"""
    config_path = project_root / "config.json"
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def call_deepseek_api(prompt: str) -> Optional[str]:
    """调用Deepseek API"""
    config = load_config()
    if not config:
        logger.error("❌ 无法加载配置文件")
        return None
    
    deepseek_config = config.get('ai_services', {}).get('deepseek', {})
    if not deepseek_config.get('enabled'):
        logger.error("❌ Deepseek服务未启用")
        return None
    
    api_url = deepseek_config.get('api_url')
    api_key = deepseek_config.get('api_key')
    model = deepseek_config.get('model', 'deepseek-r1-250528')
    
    if not api_url or not api_key:
        logger.error("❌ Deepseek API配置不完整")
        return None
    
    try:
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
        
        payload = {
            'model': model,
            'messages': [
                {
                    'role': 'user',
                    'content': prompt
                }
            ],
            'temperature': 0.1,
            'max_tokens': 500
        }
        
        response = requests.post(
            api_url,
            headers=headers,
            json=payload,
            timeout=60  # 增加超时时间到60秒
        )
        
        if response.status_code == 200:
            data = response.json()
            if 'choices' in data and len(data['choices']) > 0:
                content = data['choices'][0].get('message', {}).get('content', '')
                return content
            else:
                logger.warning(f"⚠️ Deepseek API返回格式异常: {data}")
                return None
        else:
            logger.error(f"❌ Deepseek API错误: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"❌ 调用Deepseek API失败: {e}")
        return None


def get_financial_data_from_deepseek(stock_code: str, stock_name: str = "", max_retries: int = 2) -> Optional[Dict]:
    """从Deepseek API获取财务数据（带重试机制）"""
    prompt = f"""请提供股票代码 {stock_code} 的以下财务数据（TTM值）：
1. 毛利率（Gross Margin，百分比）
2. PE TTM（市盈率）

请以JSON格式返回，格式如下：
{{
    "gross_margin": 数值（百分比，如25.5表示25.5%），
    "pe_ttm": 数值（如15.2）
}}

如果无法获取数据，返回null值。只返回JSON，不要其他文字。"""
    
    for attempt in range(max_retries):
        response = call_deepseek_api(prompt)
        if response:
            break
        if attempt < max_retries - 1:
            logger.debug(f"  重试 {attempt + 1}/{max_retries}...")
            time.sleep(3)
    if not response:
        return None
    
    try:
        # 尝试从响应中提取JSON
        response_clean = response.strip()
        
        # 移除可能的markdown代码块标记
        if response_clean.startswith('```json'):
            # 找到第一个```json和最后一个```之间的内容
            start_idx = response_clean.find('```json') + 7
            end_idx = response_clean.rfind('```')
            if end_idx > start_idx:
                response_clean = response_clean[start_idx:end_idx].strip()
        elif response_clean.startswith('```'):
            # 找到第一个```和最后一个```之间的内容
            start_idx = response_clean.find('```') + 3
            end_idx = response_clean.rfind('```')
            if end_idx > start_idx:
                response_clean = response_clean[start_idx:end_idx].strip()
        
        # 尝试找到JSON对象
        start_brace = response_clean.find('{')
        end_brace = response_clean.rfind('}')
        if start_brace >= 0 and end_brace > start_brace:
            response_clean = response_clean[start_brace:end_brace+1]
        
        data = json.loads(response_clean)
        return data
    except json.JSONDecodeError as e:
        logger.debug(f"解析Deepseek响应失败: {e}, 响应: {response[:200]}")
        return None
    except Exception as e:
        logger.debug(f"处理Deepseek响应失败: {e}")
        return None


def get_s1_stock_codes(warehouse: PostgresWarehouse) -> List[tuple]:
    """获取S1股票池的股票代码和名称"""
    if not warehouse.warehouse_service:
        return []
    
    session = warehouse.warehouse_service.get_session()
    try:
        query = text("""
            SELECT DISTINCT 
                dsu.ts_code,
                COALESCE(ds.name, dsu.ts_code) as stock_name
            FROM dim_stock_universe dsu
            LEFT JOIN dim_stock ds ON 
                CASE 
                    WHEN dsu.ts_code LIKE '6%' THEN ds.ts_code = dsu.ts_code || '.SH'
                    WHEN dsu.ts_code LIKE '0%' OR dsu.ts_code LIKE '3%' THEN ds.ts_code = dsu.ts_code || '.SZ'
                    ELSE ds.ts_code = dsu.ts_code
                END
            WHERE dsu.universe_type = 's1'
                AND dsu.is_active = TRUE
                AND dsu.trade_date = (SELECT MAX(trade_date) FROM dim_stock_universe WHERE universe_type = 's1')
            ORDER BY dsu.ts_code
        """)
        results = session.execute(query).fetchall()
        
        codes = []
        for row in results:
            code = row[0]
            name = row[1] if row[1] else code
            # 转换为Tushare格式
            if code.startswith('6'):
                ts_code = f"{code}.SH"
            elif code.startswith(('0', '3')):
                ts_code = f"{code}.SZ"
            else:
                ts_code = code
            codes.append((ts_code, name))
        
        return codes
    finally:
        session.close()


def get_latest_trade_date(warehouse: PostgresWarehouse) -> Optional[date]:
    """获取最新的交易日期（优先使用fact_daily_price，因为qfq可能滞后）"""
    if not warehouse.warehouse_service:
        return None
    
    session = warehouse.warehouse_service.get_session()
    try:
        # 优先从fact_daily_price获取（通常更新更及时）
        query1 = text("""
            SELECT MAX(trade_date) as latest_date
            FROM fact_daily_price
        """)
        result1 = session.execute(query1).scalar()
        
        # 如果fact_daily_price没有数据，再从qfq获取
        if result1:
            return result1
        
        query2 = text("""
            SELECT MAX(trade_date) as latest_date
            FROM fact_daily_price_qfq
        """)
        result2 = session.execute(query2).scalar()
        return result2 if result2 else None
    finally:
        session.close()


def update_daily_fundamental(
    session,
    ts_code: str,
    trade_date: date,
    gross_margin: Optional[float] = None,
    pe: Optional[float] = None
) -> bool:
    """更新fact_daily_fundamental表"""
    try:
        existing = session.query(FactDailyFundamental).filter(
            FactDailyFundamental.ts_code == ts_code,
            FactDailyFundamental.trade_date == trade_date
        ).first()
        
        if existing:
            if gross_margin is not None:
                existing.gross_margin_ttm = gross_margin
            if pe is not None:
                existing.pe_ttm = pe
        else:
            new_record = FactDailyFundamental(
                ts_code=ts_code,
                trade_date=trade_date,
                gross_margin_ttm=gross_margin,
                pe_ttm=pe,
                source='deepseek_api'
            )
            session.add(new_record)
        
        session.commit()
        return True
        
    except Exception as e:
        logger.error(f"更新 {ts_code} 数据失败: {e}")
        session.rollback()
        return False


def fill_s1_gross_margin_deepseek():
    """使用Deepseek API为S1股票池补充毛利率和PE数据"""
    logger.info("=" * 60)
    logger.info("使用Deepseek API为S1股票池补充毛利率和PE数据")
    logger.info("=" * 60)
    
    warehouse = PostgresWarehouse()
    if not warehouse.warehouse_service:
        logger.error("❌ 数据仓库未初始化")
        return
    
    # 获取S1股票代码
    s1_stocks = get_s1_stock_codes(warehouse)
    if not s1_stocks:
        logger.warning("⚠️ 没有找到S1股票")
        return
    
    logger.info(f"📊 找到 {len(s1_stocks)} 只S1股票")
    
    # 获取最新交易日期
    latest_date = get_latest_trade_date(warehouse)
    if not latest_date:
        logger.error("❌ 无法获取最新交易日期")
        return
    
    logger.info(f"📅 目标交易日期: {latest_date}")
    logger.info("")
    
    session = warehouse.warehouse_service.get_session()
    try:
        success_count = 0
        failed_count = 0
        gross_margin_filled = 0
        pe_filled = 0
        
        for idx, (ts_code, stock_name) in enumerate(s1_stocks, 1):
            try:
                # 转换代码格式（去掉.SH/.SZ后缀）
                if '.SH' in ts_code:
                    code = ts_code.replace('.SH', '')
                elif '.SZ' in ts_code:
                    code = ts_code.replace('.SZ', '')
                else:
                    code = ts_code
                
                logger.info(f"  处理 {idx}/{len(s1_stocks)}: {code}({stock_name})")
                
                # 调用Deepseek API获取财务数据（带超时保护）
                try:
                    financial_data = get_financial_data_from_deepseek(code, stock_name)
                except Exception as api_error:
                    logger.error(f"  ❌ API调用异常: {api_error}")
                    financial_data = None
                
                gross_margin = None
                pe = None
                
                if financial_data:
                    gross_margin = financial_data.get('gross_margin')
                    pe = financial_data.get('pe_ttm')
                
                # 更新数据库
                if gross_margin is not None or pe is not None:
                    success = update_daily_fundamental(
                        session,
                        ts_code,
                        latest_date,
                        gross_margin=gross_margin,
                        pe=pe
                    )
                    
                    if success:
                        success_count += 1
                        if gross_margin:
                            gross_margin_filled += 1
                        if pe:
                            pe_filled += 1
                        
                        if idx % 10 == 0 or idx <= 5:
                            logger.info(f"  进度: {idx}/{len(s1_stocks)} - {code}({stock_name}): 毛利率={gross_margin if gross_margin else '无'}, PE={pe if pe else '无'}")
                    else:
                        failed_count += 1
                else:
                    if idx <= 5:
                        logger.warning(f"  ⚠️ {code} 未获取到数据")
                    failed_count += 1
                
                # 延迟，避免请求过快（Deepseek API可能需要更长时间）
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"  ❌ 处理 {ts_code} 失败: {e}")
                failed_count += 1
                continue
        
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"✅ 补充完成")
        logger.info(f"  成功更新: {success_count} 只")
        logger.info(f"  补充毛利率: {gross_margin_filled} 只")
        logger.info(f"  补充PE: {pe_filled} 只")
        logger.info(f"  失败: {failed_count} 只")
        logger.info("=" * 60)
        
    finally:
        session.close()


if __name__ == '__main__':
    try:
        fill_s1_gross_margin_deepseek()
    except KeyboardInterrupt:
        logger.info("\n⚠️ 用户中断")
    except Exception as e:
        logger.error(f"❌ 补充失败: {e}", exc_info=True)
        sys.exit(1)

