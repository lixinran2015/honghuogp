"""
策略引擎说明API接口
返回7个策略模型的说明（静态JSON）
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, List
import logging

from backend.strategy.volume_price import get_all_volume_price_patterns

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/engines", tags=["engines"])


@router.get("")
async def get_strategy_engines() -> Dict:
    """
    获取策略引擎说明
    
    Returns:
        dict: 包含7个策略模型说明的字典
    """
    try:
        logger.info("📥 收到策略引擎说明请求")
        
        engines = [
            {
                "name": "量价关系模型",
                "description": "根据成交量和价格变化，识别12种量价形态（量增价升、量增价平、量增价跌、量缩价涨、量缩价跌、量平价升、量平价跌、无量价升、无量价平、无量价跌、天量天价、地量地价），并给出操作建议（买入、持有、减仓、观望）。",
                "fields": [
                    "成交量（volume）",
                    "5日均量（avgVolume5）",
                    "涨跌幅（changePct）",
                    "当前价格（lastPrice）",
                    "52周最高价（high52w）",
                    "52周最低价（low52w）",
                    "昨收价（closePrev）"
                ],
                "output": "量价形态类型、操作建议、形态解读",
                "patterns": get_all_volume_price_patterns(),  # 详细的12种量价形态说明
                "examples": [
                    {
                        "pattern": "量增价升",
                        "advice": "买入",
                        "description": "成交量持续增加，股价趋势转为上升，多头主动进攻，是短中线最佳买入信号。",
                        "example": "在回调不破5日线时，可以小仓试探性买入。",
                        "color": "positive"
                    },
                    {
                        "pattern": "量增价跌",
                        "advice": "减仓/卖出",
                        "description": "高位放量下跌，获利盘集中出逃，是明显的卖出信号。",
                        "example": "建议减仓或止损，避免深度回调。",
                        "color": "negative"
                    },
                    {
                        "pattern": "量缩价跌",
                        "advice": "观望",
                        "description": "缩量下跌，空头动能有限，以观望为主，等待新的放量方向。",
                        "example": "可关注是否出现地量地价信号。",
                        "color": "neutral"
                    }
                ]
            },
            {
                "name": "达尔文长期策略",
                "description": "筛选财务稳健、中期趋势向上、行业热度适中的优质公司，适合中长期持有。通过财务健康、盈利质量、行业地位、估值合理性四层筛选，结合趋势验证和板块热度加权，给出最终评分。",
                "fields": [
                    "ROE（净资产收益率）",
                    "经营性现金流（op_cf）",
                    "负债率（debt_ratio）",
                    "毛利率（gross_margin）",
                    "净利润（net_profit）",
                    "PE（市盈率）",
                    "PB（市净率）",
                    "MA20、MA60（移动平均线）",
                    "板块热度（sectorHeat）"
                ],
                "output": "最终得分（finalScore）、趋势分数（trendScore）、板块热度（sectorHeat）、长期标签（longTermTag）",
                "steps": [
                    {
                        "step": 1,
                        "name": "财务健康筛选",
                        "description": "ROE≥12%，经营性现金流为正且与净利润匹配，负债率在20%-70%区间，无连续2年大额亏损。",
                        "example": "筛选出财务稳健、现金流健康的优质公司。"
                    },
                    {
                        "step": 2,
                        "name": "盈利质量筛选",
                        "description": "最近3-5年净利润趋势稳步增长或小幅波动，毛利率保持稳定或略有提升。",
                        "example": "确保公司盈利质量高，具备持续盈利能力。"
                    },
                    {
                        "step": 3,
                        "name": "行业地位筛选",
                        "description": "行业本身不是长期衰退行业，公司市值或营收规模处于行业中上（市值排名前30%）。",
                        "example": "优先选择行业龙头或细分领域领先公司。"
                    },
                    {
                        "step": 4,
                        "name": "估值合理性筛选",
                        "description": "当前PE或PB在5年分位数10%-70%区间内→核心持仓，>80%→观察池。",
                        "example": "避免高估股票，选择估值合理的优质标的。"
                    },
                    {
                        "step": 5,
                        "name": "趋势验证",
                        "description": "价格在MA60上方（至少1.01倍），MA20在MA60上方（多头排列），计算趋势分数（0~1）。",
                        "example": "确保中期趋势向上，避免逆势操作。"
                    },
                    {
                        "step": 6,
                        "name": "板块热度加权",
                        "description": "使用波段热度分数（swing_heat_score），0~20分映射到0~1，作为环境因子。",
                        "example": "优先选择板块热度适中的股票，避免过热或过冷板块。"
                    }
                ],
                "formula": "最终得分 = 财务评分 × 0.6 + 趋势分数 × 0.25 + 板块热度因子 × 0.15",
                "examples": [
                    {
                        "stock": "600519.SH",
                        "name": "贵州茅台",
                        "finalScore": 72.2,
                        "trendScore": 1.0,
                        "sectorHeat": 14.96,
                        "longTermTag": "核心持仓",
                        "reason": "财务健康，ROE>25%，趋势向上，板块热度适中"
                    }
                ]
            },
            {
                "name": "波段回踩策略",
                "description": "筛选上升趋势中合理回踩的股票，来自热度较高的板块，适合波段持有。通过识别上升趋势、回踩阶段、量价结构、支撑位四个步骤，找到最佳买入时机。",
                "fields": [
                    "MA10、MA20、MA60（移动平均线）",
                    "收盘价（close）",
                    "涨跌幅（changePct）",
                    "成交量（volume）",
                    "5日均量（avgVolume5）",
                    "成交额（amount）",
                    "板块热度（swing_heat_score）"
                ],
                "output": "回踩幅度（pullback_pct）、量价形态（volumePricePattern）、支撑位类型（support_type）、推荐理由（reason）",
                "steps": [
                    {
                        "step": 1,
                        "name": "识别上升趋势",
                        "description": "MA10 > MA20（中期多头），close > MA10的天数在最近10日内≥3天，最近20日内有明显涨幅（≥10%）。",
                        "example": "确保股票处于上升趋势中，避免逆势操作。"
                    },
                    {
                        "step": 2,
                        "name": "识别回踩阶段",
                        "description": "当前close相对于最近高点回落5%-15%，今日涨跌幅在-3%~+2%区间，volume_ratio≤0.8（缩量回踩最优）。",
                        "example": "找到上升趋势中的合理回踩点，是较好的买入时机。"
                    },
                    {
                        "step": 3,
                        "name": "量价结构筛选",
                        "description": "优先保留量缩价跌、量缩价平、量缩价涨、量平价跌等形态，说明回踩健康。",
                        "example": "缩量回踩说明抛压不大，是健康的调整信号。"
                    },
                    {
                        "step": 4,
                        "name": "支撑位筛选",
                        "description": "close接近MA20或MA60，|close - MA20| / MA20 ≤ 2% 或接近前低支撑。",
                        "example": "在支撑位附近买入，风险相对较小，止损位明确。"
                    }
                ],
                "formula": "最终得分 = 基础波段得分 × 0.5 + 趋势分数 × 0.3 + 板块热度因子 × 0.2",
                "examples": [
                    {
                        "stock": "000001.SZ",
                        "name": "平安银行",
                        "pullback_pct": 8.5,
                        "volumePricePattern": "量缩价跌",
                        "support_type": "MA20",
                        "reason": "上升趋势中回踩，板块热度8.5，趋势分数0.75"
                    }
                ]
            },
            {
                "name": "短线动量策略",
                "description": "筛选热门板块中的龙头或强势股票，具有明显的短线动能，适合短线操作。通过锁定热点板块、筛选强势个股、验证量价结构、识别龙头四个步骤，找到最具爆发力的股票。",
                "fields": [
                    "涨幅（changePct）",
                    "换手率（turnoverRate）",
                    "成交额（amount）",
                    "成交量（volume）",
                    "5日均量（avgVolume5）",
                    "板块热度（short_heat_score）",
                    "是否涨停（is_limit_up）"
                ],
                "output": "综合得分（score）、量价形态（volumePricePattern）、龙头角色（leader_role）、推荐理由（reason）",
                "steps": [
                    {
                        "step": 1,
                        "name": "锁定热点板块",
                        "description": "识别板块涨幅排在前5或板块涨幅≥2%的热点板块，只筛选热点板块内的股票。",
                        "example": "优先选择市场关注度高的板块，资金集中度高。"
                    },
                    {
                        "step": 2,
                        "name": "筛选强势个股",
                        "description": "涨幅≥3%，换手率≥5%，成交额≥1亿，排除ST和退市股票。",
                        "example": "确保股票具有足够的流动性和市场关注度。"
                    },
                    {
                        "step": 3,
                        "name": "验证量价结构",
                        "description": "优先保留量增价升、量平价升等健康量价形态，说明资金积极介入。",
                        "example": "量价配合良好，说明上涨有资金支撑，可持续性强。"
                    },
                    {
                        "step": 4,
                        "name": "识别龙头",
                        "description": "按板块内部排序，优先选择涨停股票，其次按涨幅、成交额、换手率综合排序，每个板块取前1-3名。",
                        "example": "龙头股通常具有更强的爆发力和持续性，是短线操作的首选。"
                    }
                ],
                "formula": "综合得分 = 涨停加分（1000分）+ 涨幅×10 + 成交额/1亿×2 + 换手率加分（10-30%区间最优）",
                "examples": [
                    {
                        "stock": "002241.SZ",
                        "name": "歌尔股份",
                        "changePct": 8.5,
                        "turnoverRate": 12.3,
                        "amount": 15.8,
                        "is_limit_up": False,
                        "volumePricePattern": "量增价升",
                        "leader_role": "leader",
                        "reason": "热门板块强势股，板块热度12.5，动量分数0.85，龙头角色=leader"
                    }
                ]
            },
            {
                "name": "龙头识别模型",
                "description": "根据涨幅、换手率、成交额等指标识别板块龙头股。优先考虑涨幅前排、换手率健康（1%-10%）、成交额大的股票。",
                "fields": [
                    "涨幅（changePct）",
                    "换手率（turnoverRate）",
                    "成交额（amount）",
                    "股票代码（code）",
                    "股票名称（name）"
                ],
                "output": "龙头股信息（代码、名称、涨幅、换手率、成交额）",
                "examples": [
                    {
                        "sector": "半导体",
                        "leader": {
                            "code": "sz000100",
                            "name": "TCL科技",
                            "changePct": 5.20,
                            "turnoverRate": 3.5,
                            "amount": 500000000
                        }
                    }
                ]
            },
            {
                "name": "情绪周期模型",
                "description": "识别市场情绪周期（冰点、回暖、高潮、退潮）。根据市场整体表现、涨停数量、跌停数量、资金流向等判断当前市场情绪阶段。",
                "fields": [
                    "市场整体涨幅",
                    "涨停股票数量",
                    "跌停股票数量",
                    "资金净流入",
                    "成交量变化"
                ],
                "output": "情绪周期阶段（冰点/回暖/高潮/退潮）",
                "examples": [
                    {
                        "stage": "回暖",
                        "description": "市场情绪逐步恢复，涨停数量增加，资金开始流入"
                    }
                ]
            },
            {
                "name": "主力吸筹模型",
                "description": "识别主力资金吸筹行为。通过分析换手率、成交额、价格波动等判断主力是否在吸筹。",
                "fields": [
                    "换手率（turnoverRate）",
                    "成交额（amount）",
                    "价格波动（volatility）",
                    "资金流向"
                ],
                "output": "主力吸筹程度（高/中/低）",
                "examples": [
                    {
                        "stock": "sh600519",
                        "name": "贵州茅台",
                        "accumulation": "高",
                        "reason": "换手率适中（2-4%），成交额放大，价格波动小"
                    }
                ]
            },
            {
                "name": "估值模型",
                "description": "评估股票估值水平。结合PE、PB、ROE等财务指标，以及历史估值分位数，判断股票是否被低估或高估。",
                "fields": [
                    "PE（市盈率）",
                    "PB（市净率）",
                    "ROE（净资产收益率）",
                    "历史估值分位数"
                ],
                "output": "估值水平（低估/合理/高估）",
                "examples": [
                    {
                        "stock": "sh600519",
                        "name": "贵州茅台",
                        "valuation": "合理",
                        "pe": 35.2,
                        "pb": 8.5,
                        "roe": 25.3
                    }
                ]
            },
            {
                "name": "多源数据融合模型（数据仓库清洗&合并）",
                "description": "整合多个数据源（AkShare、Tushare、Eastmoney）的数据，进行清洗、去重、合并，生成统一的数据仓库。支持Raw Layer（原始数据）、Clean Layer（清洗数据）、Service Layer（服务层）三层架构。",
                "fields": [
                    "数据源标识（source）",
                    "数据质量等级（data_quality）",
                    "实际参与合并的数据源（sources_used）"
                ],
                "output": "清洗后的统一数据",
                "examples": [
                    {
                        "ts_code": "600519.SH",
                        "trade_date": "2025-11-17",
                        "close": 1680.0,
                        "sources_used": ["tushare", "akshare"],
                        "data_quality": "A"
                    }
                ]
            },
            {
                "name": "板块热度模型",
                "description": "计算板块热度评分（0-100）。综合考虑板块涨幅、资金流入、龙头涨幅、涨停数量、股票数量等因素，给出板块热度评分。",
                "fields": [
                    "板块平均涨幅（sector_change_pct）",
                    "资金流入（money_inflow）",
                    "龙头股涨幅（leader_change_pct）",
                    "涨停股票数量（limit_up_count）",
                    "板块内股票数量（stock_count）"
                ],
                "output": "板块热度评分（heatScore，0-100）",
                "examples": [
                    {
                        "sector": "半导体",
                        "heatScore": 92,
                        "sector_change_pct": 3.5,
                        "money_inflow": 15.2,
                        "leader_change_pct": 8.5,
                        "limit_up_count": 5
                    }
                ]
            }
        ]
        
        logger.info(f"✅ 返回 {len(engines)} 个策略引擎说明")
        
        return {
            "success": True,
            "engines": engines,
            "count": len(engines)
        }
        
    except Exception as e:
        logger.error(f"❌ 获取策略引擎说明失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取策略引擎说明失败，请稍后重试")

