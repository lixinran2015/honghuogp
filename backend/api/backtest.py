"""
量化回测 API
- 策略回测
- 绩效指标查询
- 策略比较
"""

from fastapi import APIRouter, Query, Body, HTTPException
from typing import Dict, Optional, List, Any
from datetime import date, datetime, timedelta
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/backtest", tags=["量化回测"])

# 延迟加载引擎
_backtest_engine = None


def get_backtest_engine():
    global _backtest_engine
    if _backtest_engine is None:
        from backend.services.backtest.backtest_engine import BacktestEngine
        _backtest_engine = BacktestEngine()
    return _backtest_engine


@router.get("/strategies")
async def list_strategies() -> Dict:
    """
    获取所有可用策略列表
    """
    from backend.services.backtest.backtest_engine import get_available_strategies
    
    strategies = get_available_strategies()
    return {
        "success": True,
        "strategies": [
            {
                "id": sid,
                "name": s.name,
                "description": _get_strategy_description(sid),
            }
            for sid, s in strategies.items()
        ],
    }


def _get_strategy_description(strategy_id: str) -> str:
    """获取策略描述"""
    descriptions = {
        "ma_5_20": "5日/20日均线金叉买入，死叉卖出",
        "ma_10_30": "10日/30日均线金叉买入，死叉卖出",
        "ma_20_60": "20日/60日均线金叉买入，死叉卖出（中长线）",
        "new_high_60": "突破60日新高买入，跌破10日线卖出",
        "new_high_120": "突破120日新高买入，跌破20日线卖出",
        "rsi_14": "RSI(14) 超卖(<30)买入，超买(>70)卖出",
        "rsi_7": "RSI(7) 超卖(<25)买入，超买(>75)卖出（激进）",
    }
    return descriptions.get(strategy_id, "自定义策略")


def _infer_base_strategy_and_position(
    base_strategy_id: str,
    strategy_config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    根据策略配置中的文字信息，推断更合适的基础策略 + 仓位比例。

    - 如果前端明确选择了非默认 base_strategy_id，则优先尊重前端选择；
    - 仅当前端传入默认值（ma_20_60）时，才尝试用规则文本自动匹配：
        - 提到「60 日新高」→ new_high_60
        - 提到「120 日新高」→ new_high_120
        - 提到「5 日 / 20 日均线」→ ma_5_20
        - 提到「20 日 / 60 日均线」→ ma_20_60
    - 仓位仍优先取 positioning.max_position_pct（0~1），否则为 1.0。
    """
    effective_base_id = base_strategy_id

    # 仓位推断
    position_size = 1.0
    try:
        positioning = (strategy_config or {}).get("positioning") or {}
        max_pct = positioning.get("max_position_pct")
        if isinstance(max_pct, (int, float)) and 0 < max_pct <= 1:
            position_size = float(max_pct)
    except Exception:
        position_size = 1.0

    # 只有在使用默认基础策略时，才尝试从规则里智能匹配
    if base_strategy_id != "ma_20_60":
        return {"base_strategy_id": effective_base_id, "position_size": position_size}

    try:
        texts: List[str] = []
        for rule in (strategy_config or {}).get("entry_rules") or []:
            if isinstance(rule, dict):
                for key in ("name", "logic"):
                    v = rule.get(key)
                    if isinstance(v, str):
                        texts.append(v)
        for rule in (strategy_config or {}).get("exit_rules") or []:
            if isinstance(rule, dict):
                for key in ("name", "logic"):
                    v = rule.get(key)
                    if isinstance(v, str):
                        texts.append(v)

        full_text = " ".join(texts)
        text_lower = full_text.lower()

        # 关键词规则按「更具体」优先
        if any(k in full_text for k in ["120日新高", "120 日新高", "120天新高", "120d high", "120-day high"]):
            effective_base_id = "new_high_120"
        elif any(k in full_text for k in ["60日新高", "60 日新高", "60天新高", "60d high", "60-day high"]):
            effective_base_id = "new_high_60"
        elif (
            ("5日" in full_text and "20日" in full_text and "均线" in full_text)
            or "5/20" in full_text
            or "5-20" in full_text
        ):
            effective_base_id = "ma_5_20"
        elif (
            ("20日" in full_text and "60日" in full_text and "均线" in full_text)
            or "20/60" in full_text
            or "20-60" in full_text
        ):
            effective_base_id = "ma_20_60"
        else:
            # 英文场景简单兜底
            if "breakout" in text_lower and ("60" in text_lower or "sixty" in text_lower):
                effective_base_id = "new_high_60"
            elif "breakout" in text_lower and ("120" in text_lower or "one hundred twenty" in text_lower):
                effective_base_id = "new_high_120"

    except Exception as e:
        logger.debug("从策略配置推断基础策略失败，将使用默认值: %s", e)

    return {"base_strategy_id": effective_base_id, "position_size": position_size}


@router.post("/strategy-config/run")
async def run_backtest_with_config(
    symbol: str = Body(..., description="股票代码，如 000001.SZ"),
    start_date: str = Body(..., description="开始日期 YYYY-MM-DD"),
    end_date: str = Body(None, description="结束日期 YYYY-MM-DD，默认今天"),
    initial_capital: float = Body(100000, description="初始资金"),
    base_strategy_id: str = Body(
        "ma_20_60",
        description="作为执行载体的基础策略ID（如 ma_20_60 / new_high_60 等）",
    ),
    strategy_config: Dict[str, Any] = Body(
        ..., description="AI 策略助手生成的策略配置 JSON"
    ),
) -> Dict:
    """
    使用「策略配置 JSON」作为上下文，调用内置基础策略进行回测。

    设计说明（MVP）：
    - 真正的买卖逻辑仍由现有 BacktestEngine + 简单基础策略负责（如 ma_20_60）
    - strategy_config 目前主要用于：
        - 记录策略名称 / 说明，回传给前端展示
        - 从其中的 positioning 字段读取仓位信息（如 max_position_pct）映射为 position_size
    - 后续可以逐步扩展，将 entry_rules/exit_rules 映射为更细粒度的策略逻辑
    """
    try:
        from backend.services.backtest.backtest_engine import (
            get_available_strategies,
            BacktestEngine,
        )

        # 先根据配置智能推断基础策略 + 仓位
        inferred = _infer_base_strategy_and_position(base_strategy_id, strategy_config)
        effective_base_id = inferred["base_strategy_id"]
        position_size = inferred["position_size"]

        strategies = get_available_strategies()
        if effective_base_id not in strategies:
            raise HTTPException(status_code=400, detail=f"基础策略不存在: {effective_base_id}")

        strategy = strategies[effective_base_id]

        # 解析日期
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else date.today()
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式错误，应为 YYYY-MM-DD")

        engine = BacktestEngine(initial_capital=initial_capital)
        result = engine.run_backtest(
            strategy=strategy,
            symbol=symbol,
            start_date=start_dt,
            end_date=end_dt,
            position_size=position_size,
        )

        if result is None:
            raise HTTPException(
                status_code=404,
                detail="回测失败，可能没有足够的历史数据或数据质量不足",
            )

        payload = result.to_dict()
        payload["strategy_meta"] = {
            "base_strategy_id": base_strategy_id,  # 前端传入的原始值
            "effective_base_strategy_id": effective_base_id,  # 实际使用的基础策略
            "ai_strategy_name": strategy_config.get("name"),
            "ai_strategy_universe": strategy_config.get("universe"),
            "ai_strategy_objective": (strategy_config.get("evaluation") or {}).get("notes"),
        }
        payload["used_position_size"] = position_size
        payload["original_strategy_config"] = strategy_config

        return {"success": True, **payload}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"策略配置回测失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="策略配置回测失败")


@router.post("/run")
async def run_backtest(
    strategy_id: str = Body(..., description="策略ID"),
    symbol: str = Body(..., description="股票代码"),
    start_date: str = Body(..., description="开始日期 YYYY-MM-DD"),
    end_date: str = Body(None, description="结束日期 YYYY-MM-DD，默认今天"),
    initial_capital: float = Body(100000, description="初始资金"),
    position_size: float = Body(1.0, description="仓位比例 0-1"),
) -> Dict:
    """
    运行单只股票的策略回测
    
    返回完整回测结果，包括：
    - 总收益率、年化收益率
    - 夏普比率
    - 最大回撤
    - 胜率、盈亏比
    - 交易记录
    - 每日净值曲线
    """
    try:
        from backend.services.backtest.backtest_engine import get_available_strategies, BacktestEngine
        
        # 获取策略
        strategies = get_available_strategies()
        if strategy_id not in strategies:
            raise HTTPException(status_code=400, detail=f"策略不存在: {strategy_id}")
        
        strategy = strategies[strategy_id]
        
        # 解析日期
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else date.today()
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式错误，应为 YYYY-MM-DD")

        # 创建引擎并运行回测
        engine = BacktestEngine(initial_capital=initial_capital)
        result = engine.run_backtest(
            strategy=strategy,
            symbol=symbol,
            start_date=start_dt,
            end_date=end_dt,
            position_size=position_size,
        )

        if result is None:
            raise HTTPException(status_code=404, detail="回测失败，可能没有足够的历史数据")

        return {"success": True, **result.to_dict()}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"回测失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="回测失败")


@router.post("/compare")
async def compare_strategies(
    symbol: str = Body(..., description="股票代码"),
    strategy_ids: List[str] = Body(None, description="策略ID列表，不传则比较所有策略"),
    start_date: str = Body(..., description="开始日期 YYYY-MM-DD"),
    end_date: str = Body(None, description="结束日期 YYYY-MM-DD"),
    initial_capital: float = Body(100000, description="初始资金"),
) -> Dict:
    """
    比较多个策略在同一只股票上的表现
    
    结果按收益率排序
    """
    try:
        from backend.services.backtest.backtest_engine import get_available_strategies, BacktestEngine
        
        all_strategies = get_available_strategies()
        
        # 选择要比较的策略
        if strategy_ids:
            strategies = [all_strategies[sid] for sid in strategy_ids if sid in all_strategies]
        else:
            strategies = list(all_strategies.values())
        
        if not strategies:
            raise HTTPException(status_code=400, detail="没有有效的策略")
        
        # 解析日期
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else date.today()
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式错误，应为 YYYY-MM-DD")

        # 运行比较
        engine = BacktestEngine(initial_capital=initial_capital)
        results = engine.compare_strategies(
            strategies=strategies,
            symbol=symbol,
            start_date=start_dt,
            end_date=end_dt,
        )

        return {
            "success": True,
            "symbol": symbol,
            "period": f"{start_date} ~ {end_date or date.today().isoformat()}",
            "strategy_count": len(results),
            "results": results,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"策略比较失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="策略比较失败")


@router.post("/batch")
async def batch_backtest(
    strategy_id: str = Body(..., description="策略ID"),
    symbols: List[str] = Body(..., description="股票代码列表"),
    start_date: str = Body(..., description="开始日期"),
    end_date: str = Body(None, description="结束日期"),
    initial_capital: float = Body(100000, description="初始资金"),
) -> Dict:
    """
    批量回测：同一策略测试多只股票
    
    用于评估策略的普适性
    """
    try:
        from backend.services.backtest.backtest_engine import get_available_strategies, BacktestEngine
        
        strategies = get_available_strategies()
        if strategy_id not in strategies:
            raise HTTPException(status_code=400, detail=f"策略不存在: {strategy_id}")
        
        strategy = strategies[strategy_id]
        
        # 解析日期
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else date.today()
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式错误，应为 YYYY-MM-DD")

        # 限制股票数量
        symbols = symbols[:20]
        
        engine = BacktestEngine(initial_capital=initial_capital)
        results = []
        
        for symbol in symbols:
            try:
                result = engine.run_backtest(
                    strategy=strategy,
                    symbol=symbol,
                    start_date=start_dt,
                    end_date=end_dt,
                )
                if result:
                    results.append({
                        "symbol": symbol,
                        "total_return": round(result.total_return * 100, 2),
                        "annual_return": round(result.annual_return * 100, 2),
                        "sharpe_ratio": round(result.sharpe_ratio, 3),
                        "max_drawdown": round(result.max_drawdown * 100, 2),
                        "win_rate": round(result.win_rate * 100, 2),
                        "total_trades": result.total_trades,
                    })
            except Exception as e:
                logger.debug(f"回测 {symbol} 失败: {e}")
        
        # 统计汇总
        if results:
            avg_return = sum(r["total_return"] for r in results) / len(results)
            avg_sharpe = sum(r["sharpe_ratio"] for r in results) / len(results)
            avg_drawdown = sum(r["max_drawdown"] for r in results) / len(results)
            avg_win_rate = sum(r["win_rate"] for r in results) / len(results)
            positive_count = sum(1 for r in results if r["total_return"] > 0)
        else:
            avg_return = avg_sharpe = avg_drawdown = avg_win_rate = 0
            positive_count = 0
        
        # 按收益排序
        results.sort(key=lambda x: x["total_return"], reverse=True)
        
        return {
            "success": True,
            "strategy_name": strategy.name,
            "period": f"{start_date} ~ {end_date or date.today().isoformat()}",
            "tested_count": len(results),
            "summary": {
                "avg_return": round(avg_return, 2),
                "avg_sharpe": round(avg_sharpe, 3),
                "avg_max_drawdown": round(avg_drawdown, 2),
                "avg_win_rate": round(avg_win_rate, 2),
                "positive_ratio": round(positive_count / len(results) * 100, 2) if results else 0,
            },
            "results": results,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量回测失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="批量回测失败")


@router.get("/quick-test")
async def quick_test(
    symbol: str = Query(..., description="股票代码"),
    days: int = Query(365, description="回测天数"),
) -> Dict:
    """
    快速测试：用所有策略测试一只股票过去N天的表现
    """
    try:
        from backend.services.backtest.backtest_engine import get_available_strategies, BacktestEngine

        end_dt = date.today()
        start_dt = end_dt - timedelta(days=days)

        strategies = get_available_strategies()
        engine = BacktestEngine()

        results = engine.compare_strategies(
            strategies=list(strategies.values()),
            symbol=symbol,
            start_date=start_dt,
            end_date=end_dt,
        )

        return {
            "success": True,
            "symbol": symbol,
            "period": f"{start_dt.isoformat()} ~ {end_dt.isoformat()}",
            "days": days,
            "best_strategy": results[0] if results else None,
            "all_results": results,
        }

    except Exception as e:
        logger.error(f"快速测试失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="快速测试失败")


# ========== 龙头策略回测接口 (Phase 6) ==========

@router.post("/leader/run")
async def run_leader_backtest(
    start_date: str = Body(..., description="开始日期 YYYY-MM-DD"),
    end_date: str = Body(None, description="结束日期 YYYY-MM-DD，默认今天"),
    min_grade: str = Body("A", description="最低评级 S/A/B/C"),
    entry_threshold: int = Body(65, description="入池阈值"),
    stop_loss_pct: float = Body(-3.0, description="止损比例%"),
    take_profit_1st: float = Body(10.0, description="第一止盈位%"),
    take_profit_2nd: float = Body(20.0, description="第二止盈位%"),
    max_holding_days: int = Body(5, description="最大持仓天数"),
    initial_capital: float = Body(100000.0, description="初始资金"),
) -> Dict:
    """
    龙头策略回测

    基于多因子评分系统的龙头策略回测
    """
    try:
        from backend.services.leader_tracking.backtest_engine import BacktestEngine

        # 解析日期
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else date.today()
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式错误，应为 YYYY-MM-DD")

        strategy_config = {
            'min_grade': min_grade,
            'entry_threshold': entry_threshold,
            'stop_loss_pct': stop_loss_pct,
            'take_profit_1st': take_profit_1st,
            'take_profit_2nd': take_profit_2nd,
            'max_holding_days': max_holding_days,
        }

        engine = BacktestEngine(
            start_date=start_dt,
            end_date=end_dt,
            initial_capital=initial_capital,
        )

        result = engine.run_backtest(strategy_config)

        if not result.get('success'):
            raise HTTPException(status_code=500, detail=result.get('error', '回测失败'))

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"龙头策略回测失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"龙头策略回测失败: {str(e)}")


@router.post("/leader/optimize")
async def optimize_leader_params(
    start_date: str = Body(..., description="开始日期 YYYY-MM-DD"),
    end_date: str = Body(None, description="结束日期 YYYY-MM-DD，默认今天"),
) -> Dict:
    """
    龙头策略参数优化

    网格搜索最优参数组合
    """
    try:
        from backend.services.leader_tracking.backtest_engine import BacktestEngine

        # 解析日期
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else date.today()
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式错误，应为 YYYY-MM-DD")

        engine = BacktestEngine(
            start_date=start_dt,
            end_date=end_dt,
        )

        param_grid = {
            'min_grade': ['A', 'B'],
            'entry_threshold': [60, 65, 70, 75],
        }

        result = engine.optimize_params(param_grid)

        if not result.get('success'):
            raise HTTPException(status_code=500, detail=result.get('error', '优化失败'))

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"参数优化失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"参数优化失败: {str(e)}")


@router.post("/leader/analyze")
async def analyze_leader_performance(
    total_return: float = Body(0.25, description="总收益率"),
    annualized_return: float = Body(0.30, description="年化收益率"),
    max_drawdown: float = Body(-0.15, description="最大回撤"),
    win_rate: float = Body(0.48, description="胜率"),
    profit_loss_ratio: float = Body(1.6, description="盈亏比"),
    sharpe_ratio: float = Body(1.4, description="夏普比率"),
    trade_count: int = Body(50, description="交易次数"),
) -> Dict:
    """
    龙头策略绩效分析

    分析回测结果，生成评估报告
    """
    try:
        from backend.services.leader_tracking.backtest_engine import PerformanceAnalyzer

        backtest_result = {
            'result': {
                'total_return': total_return,
                'annualized_return': annualized_return,
                'max_drawdown': max_drawdown,
                'win_rate': win_rate,
                'profit_loss_ratio': profit_loss_ratio,
                'sharpe_ratio': sharpe_ratio,
                'trade_count': trade_count,
            }
        }

        analyzer = PerformanceAnalyzer()
        result = analyzer.analyze(backtest_result)

        return result

    except Exception as e:
        logger.error(f"绩效分析失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"绩效分析失败: {str(e)}")


@router.get("/leader/benchmarks")
async def get_leader_benchmarks() -> Dict:
    """
    获取龙头策略绩效基准
    """
    return {
        'success': True,
        'benchmarks': {
            'win_rate': {'min': 0.40, 'target': 0.45, 'excellent': 0.50},
            'profit_loss_ratio': {'min': 1.3, 'target': 1.5, 'excellent': 2.0},
            'max_drawdown': {'max': -0.20, 'good': -0.15, 'excellent': -0.10},
            'sharpe_ratio': {'min': 1.0, 'target': 1.5, 'excellent': 2.0},
        },
    }
