"""
达尔文策略专用数据服务
从PostgreSQL数据仓库批量获取财务数据和行业信息
"""

import logging
from typing import Dict, List, Optional, Any
from sqlalchemy import text

from data_warehouse.db import get_shared_engine
from backend.utils.stock_code_utils import codes_to_ts_codes_with_mapping

logger = logging.getLogger(__name__)

# 财务数据查询的最小日期（避免查全表）
MIN_FUNDAMENTAL_DATE = '2024-01-01'


class DarwinDataService:
    """达尔文策略数据服务"""

    def __init__(self):
        """初始化数据服务"""
        self.engine = get_shared_engine()
        logger.info("✅ DarwinDataService 已初始化")

    def get_financial_data_batch(self, stock_codes: List[str]) -> Dict[str, Dict]:
        """
        批量获取股票财务数据

        Args:
            stock_codes: 股票代码列表（6位数字，如'600021'）

        Returns:
            dict: {stock_code: {财务指标...}}
        """
        ts_codes, code_mapping = codes_to_ts_codes_with_mapping(stock_codes)
        if not ts_codes:
            return {}

        try:
            with self.engine.connect() as conn:
                daily_rows = self._fetch_latest_daily_fundamental(conn, ts_codes)
                balance_dict = self._fetch_latest_balance_sheet(conn, ts_codes)

                financial_dict = {}
                for row in daily_rows:
                    ts_code = row[0]
                    clean_code = code_mapping.get(ts_code)
                    if not clean_code:
                        continue

                    balance_data = balance_dict.get(ts_code, {})
                    total_assets = balance_data.get('total_assets')
                    total_liab = balance_data.get('total_liab')
                    total_equity = (total_assets - total_liab) if total_assets is not None and total_liab is not None else None

                    financial_dict[clean_code] = self._build_financial_row(
                        row, ts_code, total_assets, total_liab, total_equity
                    )

                missing_ts = [tc for tc in ts_codes if code_mapping.get(tc) not in financial_dict]
                if missing_ts:
                    self._diagnose_missing(conn, missing_ts)

                logger.info(f"✅ 批量获取财务数据成功: {len(financial_dict)}/{len(stock_codes)} 只股票")
                return financial_dict

        except Exception as e:
            logger.error(f"❌ 批量获取财务数据失败: {e}", exc_info=True)
            return {}

    def _fetch_latest_daily_fundamental(self, conn, ts_codes: List[str]) -> List[Any]:
        """获取每只股票最新的 fact_daily_fundamental 数据"""
        q = text("""
            WITH latest_daily AS (
                SELECT ts_code, trade_date, roe_ttm, roe_lyr, pb_lyr, pb_mrq, pe_ttm,
                       gross_margin_ttm, net_margin_ttm, op_cf_ttm,
                       revenue_growth_yoy, profit_growth_yoy,
                       ROW_NUMBER() OVER (PARTITION BY ts_code ORDER BY trade_date DESC) as rn
                FROM fact_daily_fundamental
                WHERE ts_code = ANY(:ts_codes) AND trade_date >= :min_date
            )
            SELECT * FROM latest_daily WHERE rn = 1
        """)
        return conn.execute(q, {"ts_codes": ts_codes, "min_date": MIN_FUNDAMENTAL_DATE}).fetchall()

    def _fetch_latest_balance_sheet(self, conn, ts_codes: List[str]) -> Dict[str, Dict]:
        """获取每只股票最新的 fact_fundamental 资产负债表数据"""
        q = text("""
            WITH latest_fundamental AS (
                SELECT ts_code, end_date, total_asset, total_debt,
                       ROW_NUMBER() OVER (PARTITION BY ts_code ORDER BY end_date DESC) as rn
                FROM fact_fundamental
                WHERE ts_code = ANY(:ts_codes) AND end_date >= :min_date
            )
            SELECT ts_code, total_asset, total_debt FROM latest_fundamental WHERE rn = 1
        """)
        rows = conn.execute(q, {"ts_codes": ts_codes, "min_date": MIN_FUNDAMENTAL_DATE}).fetchall()
        return {
            row[0]: {
                'total_assets': float(row[1]) if row[1] is not None else None,
                'total_liab': float(row[2]) if row[2] is not None else None,
            }
            for row in rows
        }

    def _build_financial_row(
        self,
        row: Any,
        ts_code: str,
        total_assets: Optional[float],
        total_liab: Optional[float],
        total_equity: Optional[float],
    ) -> Dict:
        """从 daily 行 + 资产负债表构建财务字典"""
        debt_ratio = float(total_liab / total_assets) if total_assets and total_liab is not None else 0.0

        row_len = len(row)
        roe = float(row[2]) if row[2] is not None else 0.0
        pe = float(row[6]) if row[6] is not None else 0.0
        op_cf = float(row[9]) if row[9] is not None else 0.0
        rev_growth = float(row[10]) if row_len > 10 and row[10] is not None else 0.0
        profit_growth = float(row[11]) if row_len > 11 and row[11] is not None else 0.0

        return {
            'ts_code': ts_code,
            'trade_date': str(row[1]) if row[1] else None,
            'roe_ttm': roe,
            'roe': roe,
            'ROE': roe,
            'revenue_yoy': rev_growth,
            'revenue_growth_yoy': rev_growth,
            'revenue_growth': rev_growth,
            'profit_growth_yoy': profit_growth,
            'profit_growth': profit_growth,
            'roe_lyr': float(row[3]) if row[3] is not None else 0.0,
            'pb': float(row[4] if row[4] is not None else row[5]) if (row[4] is not None or row[5] is not None) else 0.0,
            'pe': pe,
            'pe_ttm': pe,
            'gross_margin': float(row[7]) if row[7] is not None else 0.0,
            'net_margin': float(row[8]) if row[8] is not None else 0.0,
            'operating_cashflow': op_cf,
            'op_cf': op_cf,
            'op_cf_ttm': op_cf,
            'total_assets': total_assets,
            'total_liab': total_liab,
            'total_debt': total_liab,
            'total_equity': total_equity,
            'net_assets': total_equity,
            'debt_ratio': debt_ratio,
            'total_mv': 0.0,
            'circ_mv': 0.0,
        }

    def _diagnose_missing(self, conn, missing_ts: List[str]) -> None:
        """诊断缺数据股票：明确缺哪个表"""
        if not missing_ts:
            return
        try:
            q_fd = text("""
                SELECT DISTINCT ts_code FROM fact_daily_fundamental
                WHERE ts_code = ANY(:ts_codes) AND trade_date >= :min_date
            """)
            q_ff = text("""
                SELECT DISTINCT ts_code FROM fact_fundamental
                WHERE ts_code = ANY(:ts_codes) AND end_date >= :min_date
            """)
            has_fd = set(r[0] for r in conn.execute(q_fd, {"ts_codes": missing_ts, "min_date": MIN_FUNDAMENTAL_DATE}))
            has_ff = set(r[0] for r in conn.execute(q_ff, {"ts_codes": missing_ts, "min_date": MIN_FUNDAMENTAL_DATE}))
            only_ff = has_ff - has_fd
            neither = set(missing_ts) - has_fd - has_ff
            if only_ff:
                logger.warning(
                    f"⚠️ 缺 fact_daily_fundamental（共{len(only_ff)}只，示例: {list(only_ff)[:5]}）"
                    "→ 需运行 fill_daily_fundamental_from_fact 从 fact_fundamental 补充"
                )
            if neither:
                logger.warning(
                    f"⚠️ fact_daily_fundamental 与 fact_fundamental 均无（共{len(neither)}只，示例: {list(neither)[:5]}）"
                    "→ 需运行 backfill_fundamental 回补 fact_fundamental"
                )
        except Exception as e:
            logger.debug(f"缺数据诊断失败（可忽略）: {e}")

    def get_industry_info_batch(self, stock_codes: List[str]) -> Dict[str, str]:
        """
        批量获取股票行业信息

        Args:
            stock_codes: 股票代码列表（6位数字）

        Returns:
            dict: {stock_code: industry_name}
        """
        ts_codes, code_mapping = codes_to_ts_codes_with_mapping(stock_codes)
        if not ts_codes:
            return {}

        try:
            with self.engine.connect() as conn:
                industry_dict = {}
                q_primary = text("""
                    SELECT DISTINCT ON (fss.ts_code) fss.ts_code, ds.name as sector_name
                    FROM fact_stock_sector fss
                    JOIN dim_sector ds ON fss.sector_id = ds.sector_id
                      AND (ds.sector_type = 'industry' OR ds.sector_type IS NULL)
                    WHERE fss.ts_code = ANY(:ts_codes)
                      AND fss.is_primary = TRUE
                      AND (fss.end_date IS NULL OR fss.end_date > CURRENT_DATE)
                    ORDER BY fss.ts_code, fss.start_date DESC
                """)
                for row in conn.execute(q_primary, {"ts_codes": ts_codes}):
                    ts_code, sector_name = row[0], row[1]
                    clean = code_mapping.get(ts_code)
                    if clean and sector_name:
                        industry_dict[clean] = sector_name

                missing_ts = [tc for tc in ts_codes if code_mapping.get(tc) not in industry_dict]
                if missing_ts:
                    q_fallback = text("""
                        SELECT ts_code, industry FROM dim_stock
                        WHERE ts_code = ANY(:ts_codes) AND industry IS NOT NULL AND industry != ''
                    """)
                    for row in conn.execute(q_fallback, {"ts_codes": missing_ts}):
                        ts_code, industry = row[0], row[1]
                        clean = code_mapping.get(ts_code)
                        if clean and industry:
                            industry_dict[clean] = industry

                logger.info(f"✅ 批量获取行业信息成功: {len(industry_dict)}/{len(stock_codes)} 只股票")
                return industry_dict

        except Exception as e:
            logger.error(f"❌ 批量获取行业信息失败: {e}", exc_info=True)
            return {}

    def generate_selection_reason(
        self,
        stock_data: Dict,
        financial_data: Optional[Dict] = None,
        industry: Optional[str] = None,
    ) -> str:
        """
        生成选股理由

        Args:
            stock_data: 股票数据
            financial_data: 财务数据
            industry: 行业名称

        Returns:
            str: 选股理由
        """
        reasons = []

        if financial_data:
            roe = financial_data.get('roe_ttm', financial_data.get('roe', 0))
            if roe >= 15:
                reasons.append(f"ROE高达{roe:.1f}%，盈利能力强")
            elif roe >= 12:
                reasons.append(f"ROE {roe:.1f}%，财务稳健")

            pe = financial_data.get('pe_ttm', financial_data.get('pe', 0))
            if 0 < pe < 20:
                reasons.append(f"PE {pe:.1f}倍，估值合理")
            elif 20 <= pe < 30:
                reasons.append(f"PE {pe:.1f}倍，估值适中")

        if industry:
            reasons.append(f"所属{industry}行业")

        change_pct = stock_data.get('changePct', 0)
        if change_pct > 0:
            reasons.append(f"当日上涨{change_pct:.2f}%")

        if financial_data:
            total_mv = financial_data.get('total_mv', 0)
            if total_mv > 0:
                if total_mv >= 10000:
                    reasons.append("千亿市值龙头")
                elif total_mv >= 5000:
                    reasons.append("大盘蓝筹")
                elif total_mv >= 1000:
                    reasons.append("中盘成长")

        if not reasons:
            reasons.append("符合达尔文筛选标准")

        return "；".join(reasons[:4])
