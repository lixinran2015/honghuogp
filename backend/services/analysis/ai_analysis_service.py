"""
AI分析服务
封装OpenAI和Deepseek的调用逻辑
"""

import json
import re
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional
import requests

logger = logging.getLogger(__name__)

try:
    from utils.config_manager import config_manager
except (ImportError, Exception) as e:
    config_manager = None
    logger.warning(f"ConfigManager未找到或初始化失败，AI分析服务功能受限: {e}")


class AIAnalysisService:
    """AI分析服务类"""
    
    def __init__(self):
        """初始化AI分析服务"""
        self.config_manager = config_manager
    
    def _get_market_environment_data(self) -> Dict:
        """
        获取市场环境数据（用于AI分析）
        
        Returns:
            dict: 市场环境数据
        """
        try:
            from backend.services.market_data_service import MarketDataService
            
            market_service = MarketDataService()
            summary = market_service.get_market_summary()
            
            market_data = {}
            if 'sse' in summary:
                sse = summary['sse']
                market_data['sh_index'] = f"{sse.get('value', 0):.2f} ({sse.get('changePct', 0):+.2f}%)"
            
            if 'szse' in summary:
                szse = summary['szse']
                market_data['sz_index'] = f"{szse.get('value', 0):.2f} ({szse.get('changePct', 0):+.2f}%)"
            
            market_data['market_sentiment'] = '中性'  # 简化处理
            
            return market_data
            
        except Exception as e:
            logger.warning(f"获取市场环境数据失败: {e}")
            return {
                'sh_index': 'N/A',
                'sz_index': 'N/A',
                'market_sentiment': 'N/A'
            }
    
    def analyze_stock_openai(self, stock_data: Dict) -> Dict:
        """
        使用OpenAI分析股票
        
        Args:
            stock_data: 股票数据字典
            
        Returns:
            dict: 分析结果，包含score、analysis、suggestion等
        """
        try:
            if not self.config_manager:
                return {
                    'score': 'N/A',
                    'analysis': '配置管理器未初始化',
                    'suggestion': '请自行判断'
                }
            
            # 从配置获取OpenAI配置
            openai_config = self.config_manager.get_ai_config("openai")
            if not openai_config or not self.config_manager.is_ai_enabled("openai"):
                return {
                    'score': 'N/A',
                    'analysis': 'OpenAI服务未启用',
                    'suggestion': '需要在配置中启用'
                }
            
            api_key = openai_config.get("api_key", "").strip()
            if not api_key or api_key == "your-openai-api-key-here":
                return {
                    'score': 'N/A',
                    'analysis': 'OpenAI API未配置',
                    'suggestion': '需要配置API Key'
                }
            
            # 验证API Key格式
            if not api_key.startswith("sk-"):
                logger.warning(f"⚠️ OpenAI API Key格式可能不正确（不以sk-开头）")
            
            # 提取股票信息（兼容多种字段名）
            stock_name = stock_data.get('股票名称') or stock_data.get('name') or stock_data.get('名称', '未知')
            stock_code = stock_data.get('代码') or stock_data.get('code') or stock_data.get('股票代码', '未知')
            stock_price = stock_data.get('最新价') or stock_data.get('price') or stock_data.get('当前价', 0)
            stock_pct_chg = stock_data.get('涨跌幅') or stock_data.get('pct_chg') or stock_data.get('涨幅', 0)
            stock_amount = stock_data.get('成交额') or stock_data.get('amount') or stock_data.get('成交金额', 0)
            # 转换为亿元显示
            stock_amount_yi = stock_amount / 100000000 if stock_amount > 0 else 0
            stock_turnover = stock_data.get('换手率') or stock_data.get('turnover_rate') or stock_data.get('换手', 'N/A')
            
            # 如果换手率是字符串，提取数字部分
            if isinstance(stock_turnover, str):
                turnover_match = re.search(r'[\d.]+', str(stock_turnover))
                if turnover_match:
                    stock_turnover = f"{turnover_match.group()}%"
            
            # 获取市场环境数据
            market_data = self._get_market_environment_data()
            
            # 构建AI综合判断买点分析提示
            prompt = f"""
            作为专业股票分析师，请进行AI综合判断买点分析：
            
            【个股数据】
            - 名称：{stock_name}
            - 代码：{stock_code}
            - 当前价格：{stock_price}元
            - 今日涨跌幅：{stock_pct_chg}%
            - 成交额：{stock_amount_yi:.2f}亿元
            - 换手率：{stock_turnover}%
            
            【市场环境】
            - 上证指数：{market_data.get('sh_index', 'N/A')}
            - 深证指数：{market_data.get('sz_index', 'N/A')}
            - 市场情绪：{market_data.get('market_sentiment', 'N/A')}
            
            【分析要求】
            请从以下维度进行综合评分：
            1. 大环境评分（40%）：市场情绪、赛道强度
            2. 个股条件评分（60%）：涨幅区间、成交额、换手率、技术位置
            
            【输出格式】
            请以JSON格式返回：
            {{
                "score": "综合评分(0-100整数)",
                "environment_score": "大环境评分(0-100)",
                "stock_score": "个股条件评分(0-100)",
                "analysis": "综合分析要点(50字内)",
                "suggestion": "操作建议(买入/观望/卖出)",
                "position": "建议仓位(10%/20%/30%)",
                "target_profit": "目标收益(%)",
                "stop_loss": "止损线(%)",
                "risk_level": "风险等级(低/中/高)"
            }}
            
            【评分标准】
            - 涨幅≤5%：安全区，可买
            - 涨幅5-8%：分歧区，需谨慎
            - 涨幅≥8%：高风险，提示追高风险
            - 成交额≥5亿，换手率适中(5%-20%)
            - 单票≤30%仓位
            """
            
            # 使用标准的 OpenAI Chat Completions API
            base_url = openai_config.get("base_url", "https://api.openai.com/v1")
            model = openai_config.get("model", "gpt-4o-mini")
            
            # 确保base_url是正确的格式（去除末尾的/v1，避免重复）
            base_url = base_url.rstrip('/')
            if base_url.endswith("/v1"):
                base_url = base_url[:-3]  # 移除末尾的/v1
            elif base_url.endswith("/chat/completions"):
                base_url = base_url.replace("/chat/completions", "").rstrip('/')
                if base_url.endswith("/v1"):
                    base_url = base_url[:-3]
            elif base_url.endswith("/v1/chat/completions"):
                base_url = base_url.replace("/v1/chat/completions", "").rstrip('/')
            
            # 构建正确的API URL
            api_url = f"{base_url}/v1/chat/completions"
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一位专业的股票分析师，擅长进行技术分析和市场情绪判断。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.7,
                "max_tokens": 500
            }
            
            logger.info(f"📡 调用OpenAI API分析股票: {stock_code} ({stock_name})")
            
            response = requests.post(api_url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            
            # 解析JSON响应（可能包含markdown代码块）
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                content = content.split('```')[1].split('```')[0].strip()
            
            try:
                analysis_result = json.loads(content)
            except json.JSONDecodeError:
                # 如果解析失败，尝试提取关键信息
                logger.warning(f"⚠️ OpenAI返回的JSON格式异常，尝试提取关键信息")
                analysis_result = {
                    'score': self._extract_score_from_text(content),
                    'analysis': content[:100] if content else '分析完成',
                    'suggestion': self._extract_suggestion_from_text(content)
                }
            
            logger.info(f"✅ OpenAI分析完成: {stock_code}, 评分: {analysis_result.get('score', 'N/A')}")
            
            return {
                'score': analysis_result.get('score', 'N/A'),
                'analysis': analysis_result.get('analysis', '分析完成'),
                'suggestion': analysis_result.get('suggestion', '请自行判断'),
                'environment_score': analysis_result.get('environment_score'),
                'stock_score': analysis_result.get('stock_score'),
                'position': analysis_result.get('position'),
                'target_profit': analysis_result.get('target_profit'),
                'stop_loss': analysis_result.get('stop_loss'),
                'risk_level': analysis_result.get('risk_level')
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ OpenAI API请求失败: {e}")
            return {
                'score': 'N/A',
                'analysis': 'AI服务暂时不可用，请稍后重试',
                'suggestion': '请自行判断'
            }
        except Exception as e:
            logger.error(f"❌ OpenAI分析失败: {e}", exc_info=True)
            return {
                'score': 'N/A',
                'analysis': '分析失败，请稍后重试',
                'suggestion': '请自行判断'
            }
    
    def analyze_stock_deepseek(self, stock_data: Dict) -> Dict:
        """
        使用Deepseek分析股票
        
        Args:
            stock_data: 股票数据字典
            
        Returns:
            dict: 分析结果，包含score、analysis、suggestion等
        """
        try:
            if not self.config_manager:
                return {
                    'score': 'N/A',
                    'analysis': '配置管理器未初始化',
                    'suggestion': '请自行判断'
                }
            
            # 从配置获取Deepseek配置
            deepseek_config = self.config_manager.get_ai_config("deepseek")
            if not deepseek_config or not self.config_manager.is_ai_enabled("deepseek"):
                return {
                    'score': 'N/A',
                    'analysis': 'Deepseek服务未启用',
                    'suggestion': '需要在配置中启用'
                }
            
            api_url = deepseek_config.get("api_url", "").strip()
            api_key = deepseek_config.get("api_key", "").strip()
            model = deepseek_config.get("model", "deepseek-r1-250528")
            
            if not api_url or not api_key:
                return {
                    'score': 'N/A',
                    'analysis': 'Deepseek API未配置',
                    'suggestion': '需要配置API'
                }
            
            # 提取股票信息（兼容多种字段名）
            stock_name = stock_data.get('股票名称') or stock_data.get('name') or stock_data.get('名称', '未知')
            stock_code = stock_data.get('代码') or stock_data.get('code') or stock_data.get('股票代码', '未知')
            stock_price = stock_data.get('最新价') or stock_data.get('price') or stock_data.get('当前价', 0)
            stock_pct_chg = stock_data.get('涨跌幅') or stock_data.get('pct_chg') or stock_data.get('涨幅', 0)
            stock_amount = stock_data.get('成交额') or stock_data.get('amount') or stock_data.get('成交金额', 0)
            # 转换为亿元显示
            stock_amount_yi = stock_amount / 100000000 if stock_amount > 0 else 0
            stock_turnover = stock_data.get('换手率') or stock_data.get('turnover_rate') or stock_data.get('换手', 'N/A')
            
            # 获取市场环境数据
            market_data = self._get_market_environment_data()
            
            # 构建分析提示
            prompt = f"""
            作为专业股票分析师，请分析以下股票：
            
            【个股数据】
            - 名称：{stock_name}
            - 代码：{stock_code}
            - 当前价格：{stock_price}元
            - 今日涨跌幅：{stock_pct_chg}%
            - 成交额：{stock_amount_yi:.2f}亿元
            - 换手率：{stock_turnover}%
            
            【市场环境】
            - 上证指数：{market_data.get('sh_index', 'N/A')}
            - 深证指数：{market_data.get('sz_index', 'N/A')}
            
            请给出：
            1. 综合评分（0-100）
            2. 分析要点
            3. 操作建议
            """
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.7,
                "max_tokens": 500
            }
            
            logger.info(f"📡 调用Deepseek API分析股票: {stock_code} ({stock_name})")
            
            response = requests.post(api_url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            
            # 提取评分和分析
            score = self._extract_score_from_text(content)
            suggestion = self._extract_suggestion_from_text(content)
            
            logger.info(f"✅ Deepseek分析完成: {stock_code}, 评分: {score}")
            
            return {
                'score': score,
                'analysis': content[:200] if content else '分析完成',
                'suggestion': suggestion
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Deepseek API请求失败: {e}")
            return {
                'score': 'N/A',
                'analysis': 'AI服务暂时不可用，请稍后重试',
                'suggestion': '请自行判断'
            }
        except Exception as e:
            logger.error(f"❌ Deepseek分析失败: {e}", exc_info=True)
            return {
                'score': 'N/A',
                'analysis': '分析失败，请稍后重试',
                'suggestion': '请自行判断'
            }
    
    def diagnose_interpret(self, diagnosis_data: Dict, timeout: float = 5.0) -> Optional[str]:
        """
        对诊断结果进行AI解读（按需调用）
        
        Args:
            diagnosis_data: 诊断结果数据，包含：
                - ts_code: 股票代码
                - name: 股票名称
                - trade_date: 交易日期
                - advice: 诊断建议
                - result: 筛选结果（stage, score, is_started, signals, risks, failed_reasons）
                - indicators: 指标数据（price, volume, ma, technical等）
                - checks: 检查项（golden_cross, bullish_alignment, breakthrough_120d等）
            timeout: 超时时间（秒），默认5秒
            
        Returns:
            Optional[str]: AI解读文本，失败返回None
        """
        try:
            if not self.config_manager:
                logger.debug("配置管理器未初始化，跳过AI解读")
                return None
            
            # 从配置获取Deepseek配置
            deepseek_config = self.config_manager.get_ai_config("deepseek")
            if not deepseek_config:
                logger.warning("Deepseek配置未找到")
                return None

            enabled = self.config_manager.is_ai_enabled("deepseek")
            logger.info(f"Deepseek服务启用状态: enabled={enabled}, config_enabled={deepseek_config.get('enabled', 'N/A')}")

            if not enabled:
                logger.warning("Deepseek服务未启用")
                return None

            api_url = deepseek_config.get("api_url", "").strip()
            api_key = deepseek_config.get("api_key", "").strip()
            model = deepseek_config.get("model", "deepseek-r1-250528")

            if not api_url or not api_key:
                logger.debug("Deepseek API未配置，跳过AI解读")
                return None

            # 提取诊断数据
            ts_code = diagnosis_data.get('ts_code', '未知')
            name = diagnosis_data.get('name', '未知')
            trade_date = diagnosis_data.get('trade_date', '未知')
            advice = diagnosis_data.get('advice', '')
            
            result = diagnosis_data.get('result', {})
            stage = result.get('stage', '未知')
            score = result.get('score', 0)
            is_started = result.get('is_started', False)
            signals = result.get('signals', [])
            risks = result.get('risks', [])
            failed_reasons = result.get('failed_reasons', [])
            
            indicators = diagnosis_data.get('indicators', {})
            checks = diagnosis_data.get('checks', {})
            
            # 获取市场环境数据
            market_data = self._get_market_environment_data()
            
            # 构建Prompt
            prompt = self._build_diagnose_interpret_prompt(
                ts_code=ts_code,
                name=name,
                trade_date=trade_date,
                advice=advice,
                stage=stage,
                score=score,
                is_started=is_started,
                signals=signals,
                risks=risks,
                failed_reasons=failed_reasons,
                indicators=indicators,
                checks=checks,
                market_data=market_data
            )
            
            # 调用DeepSeek API
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一位专业的股票分析师，擅长解读股票启动诊断结果，提供深入、专业、易懂的分析。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.7,
                "max_tokens": 500  # 解读控制在500字内
            }
            
            logger.info(f"📡 调用DeepSeek API进行诊断解读: {ts_code} ({name}), URL: {api_url}")
            
            start_time = time.time()
            try:
                response = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
            except requests.exceptions.ConnectionError as e:
                elapsed_time = time.time() - start_time
                logger.error(f"DeepSeek API连接失败: {e}, URL: {api_url}")
                logger.error(f"   请求耗时: {elapsed_time:.2f}秒, 超时设置: {timeout}秒")
                logger.error(f"   请检查网络连接或API服务是否可用")
                return None
            except requests.exceptions.Timeout as e:
                elapsed_time = time.time() - start_time
                logger.error(f"DeepSeek API连接超时: {e}, URL: {api_url}")
                logger.error(f"   请求耗时: {elapsed_time:.2f}秒, 超时设置: {timeout}秒")
                logger.error(f"   建议：1) 检查网络连接 2) 增加timeout配置 3) 检查API服务状态")
                return None
            except requests.exceptions.ReadTimeout as e:
                elapsed_time = time.time() - start_time
                logger.error(f"DeepSeek API读取超时: {e}, URL: {api_url}")
                logger.error(f"   请求耗时: {elapsed_time:.2f}秒, 超时设置: {timeout}秒")
                logger.error(f"   可能是API响应时间过长，建议增加timeout配置")
                return None
            
            # 检查超时
            elapsed_time = time.time() - start_time
            if elapsed_time > timeout:
                logger.warning(f"DeepSeek API调用超时（{elapsed_time:.2f}s > {timeout}s）")
                return None
            
            # 检查HTTP状态码
            if response.status_code != 200:
                logger.error(f"DeepSeek API返回错误状态码: {response.status_code}, 响应: {response.text[:500]}")
                return None
            
            try:
                result_data = response.json()
            except Exception as e:
                logger.error(f"DeepSeek API响应解析失败: {e}, 响应内容: {response.text[:500]}")
                return None
            
            content = result_data.get('choices', [{}])[0].get('message', {}).get('content', '')
            
            if not content:
                logger.warning(f"DeepSeek API返回空内容，完整响应: {result_data}")
                return None
            
            # 清理内容
            interpreted_text = self._clean_interpret_text(content)
            
            logger.info(f"✅ DeepSeek诊断解读完成: {ts_code}, 耗时: {elapsed_time:.2f}s")
            return interpreted_text
            
        except requests.exceptions.Timeout:
            error_msg = f"DeepSeek API调用超时（>{timeout}s）"
            logger.warning(error_msg)
            return None
        except requests.exceptions.HTTPError as e:
            error_msg = f"DeepSeek API HTTP错误: {e.response.status_code} - {e.response.text[:200] if e.response else str(e)}"
            logger.error(error_msg)
            return None
        except requests.exceptions.RequestException as e:
            error_msg = f"DeepSeek API请求失败: {str(e)}"
            logger.error(error_msg)
            return None
        except Exception as e:
            error_msg = f"DeepSeek诊断解读失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return None
    
    def suggest_holding_to_close(self, holdings_summary: List[Dict], timeout: int = 12) -> Optional[Dict]:
        """
        操作池已满时，由 AI 从当前持仓中选出最建议优先清仓的一只及理由。
        
        Args:
            holdings_summary: 持仓摘要列表，每项含 symbol, name, profit_rate, chase_risk_score,
                             today_action, today_action_reason 等
            timeout: 请求超时秒数
            
        Returns:
            {"symbol": "000001.SZ", "reason": "一句话理由"} 或 None（失败/未配置）
        """
        try:
            if not self.config_manager:
                return None
            deepseek_config = self.config_manager.get_ai_config("deepseek")
            if not deepseek_config or not self.config_manager.is_ai_enabled("deepseek"):
                return None
            api_url = (deepseek_config.get("api_url") or "").strip()
            api_key = (deepseek_config.get("api_key") or "").strip()
            model = deepseek_config.get("model", "deepseek-chat")
            if not api_url or not api_key:
                return None
            if not holdings_summary or len(holdings_summary) < 2:
                return None
            # 专业操作手视角：构建多维度持仓摘要（持有天数、破线、龙头、回涨、策略类型）
            lines = []
            for i, h in enumerate(holdings_summary[:10], 1):
                name = h.get("name") or h.get("symbol") or ""
                symbol = h.get("symbol") or ""
                pr = h.get("profit_rate")
                pr_str = f"{pr:.1f}%" if pr is not None else "—"
                risk = h.get("chase_risk_score")
                risk_str = f"{risk:.0f}分" if risk is not None else "—"
                action = h.get("today_action") or "—"
                reason = (h.get("today_action_reason") or "")[:60]
                days = h.get("holding_days")
                days_str = f"{int(days)}天" if days is not None else "—"
                below_ma5 = "破5" if h.get("below_ma5") else "站5"
                below_ma10 = "破10" if h.get("below_ma10") else "站10"
                leader = "龙头" if h.get("is_leader") else "—"
                mainline = "主线" if h.get("in_mainline") else "—"
                sector_role = h.get("sector_leader_role") or "—"
                board = (h.get("board_type") or "—")[:6]
                rec = h.get("recovery_probability")
                rec_str = f"回涨{rec:.0f}%" if rec is not None else "—"
                lines.append(
                    f"{i}. {name}({symbol}) 盈亏{pr_str} 追高{risk_str} 建议{action} 持{days_str} {below_ma5}/{below_ma10} {leader} {mainline} {sector_role} {board} {rec_str} | {reason}"
                )
            prompt = """你是一位专业短线操作手。操作池最多保留8只股票，当前已满。请从下列持仓中选出「最建议优先清仓」的一只。

【重要】1) 今日买入（持0天）→ 不选。2) 未破5日线 → 不选，只从破5日线的标的中选。3) 有亏损时不选盈利股。4) 全部盈利时选盈利低或破位的。5) 龙头+持≤3天+亏损<3% → 不宜选。

决策优先级（按重要性）：
1) 已建议止损(close)或减仓(reduce)、且亏损或追高风险高 → 优先清仓
2) 亏损5%~10% → 建议减半仓；亏损>10% → 建议清仓；破5日线/破10日线可加重止损倾向
3) 非龙头 + 追高风险高 + 浮盈≥20% → 可止盈兑现（浮盈不足20%不宜过早清仓）
4) 持有天数长且回涨概率低、无起色 → 换仓腾位
5) 龙头+持≤3天+小幅亏损(<3%)+未破位 → 不选，给涨停后正常回调留观察期

持仓摘要（含：盈亏、追高风险、当前建议、持有天数、破5/破10、是否龙头、策略类型、回涨概率、建议理由）：
""" + "\n".join(lines) + """

仅返回一行JSON，不要其他说明。格式：{"symbol":"股票代码如000001.SZ","reason":"一句话理由（可含类型：止损/止盈/换仓/风控）"}
"""
            api_url = api_url.rstrip("/")
            if not api_url.endswith("/v1/chat/completions"):
                api_url = f"{api_url.rstrip('/')}/v1/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "你是一位专业股票顾问。只输出要求的JSON，不要解释。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 200
            }
            resp = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code != 200:
                logger.debug("建议清仓 AI 请求非200: %s", resp.status_code)
                return None
            data = resp.json()
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
            if not content:
                return None
            content = content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            parsed = json.loads(content)
            symbol = (parsed.get("symbol") or "").strip()
            reason = (parsed.get("reason") or "").strip() or "建议优先清仓"
            if symbol and reason:
                logger.info("建议清仓 AI 返回: %s %s", symbol, reason[:50])
                return {"symbol": symbol, "reason": reason}
            return None
        except Exception as e:
            logger.debug("建议清仓 AI 调用失败: %s", e)
            return None
    
    def batch_holding_actions(self, holdings_summary: List[Dict], timeout: int = 25) -> Optional[List[Dict]]:
        """
        综合判断每只持仓的操作建议：加仓、减仓、清仓、持有。
        供「每5分钟」定时任务调用，结果可缓存供前端展示。
        
        Args:
            holdings_summary: 持仓摘要列表（字段同 suggest_holding_to_close）
            timeout: 请求超时秒数
            
        Returns:
            [ {"symbol": "000001.SZ", "action": "持有"|"加仓"|"减仓"|"清仓", "reason": "一句话"}, ... ] 或 None
        """
        try:
            if not self.config_manager:
                return None
            deepseek_config = self.config_manager.get_ai_config("deepseek")
            if not deepseek_config or not self.config_manager.is_ai_enabled("deepseek"):
                return None
            api_url = (deepseek_config.get("api_url") or "").strip()
            api_key = (deepseek_config.get("api_key") or "").strip()
            model = deepseek_config.get("model", "deepseek-chat")
            if not api_url or not api_key or not holdings_summary:
                return None
            lines = []
            for i, h in enumerate(holdings_summary[:20], 1):
                name = h.get("name") or h.get("symbol") or ""
                symbol = h.get("symbol") or ""
                pr = h.get("profit_rate")
                pr_str = f"{pr:.1f}%" if pr is not None else "—"
                risk = h.get("chase_risk_score")
                risk_str = f"{risk:.0f}分" if risk is not None else "—"
                action = h.get("today_action") or "—"
                reason = (h.get("today_action_reason") or "")[:50]
                days = h.get("holding_days")
                days_str = f"{int(days)}天" if days is not None else "—"
                below_ma5 = "破5" if h.get("below_ma5") else "站5"
                below_ma10 = "破10" if h.get("below_ma10") else "站10"
                leader = "龙头" if h.get("is_leader") else "—"
                mainline = "主线" if h.get("in_mainline") else "—"
                sector_role = h.get("sector_leader_role") or "—"
                lines.append(
                    f"{i}. {name}({symbol}) 盈亏{pr_str} 追高{risk_str} 当前建议{action} 持{days_str} {below_ma5}/{below_ma10} {leader} {mainline} {sector_role} | {reason}"
                )
            prompt = """你是专业短线操作手。请对下列每只持仓给出综合操作建议：加仓、减仓、清仓、持有之一，并给一句话理由。
考虑：盈亏、追高风险、是否破位、持有天数、是否龙头、当前系统建议等。

持仓列表：
""" + "\n".join(lines) + """

仅返回一个JSON数组，不要其他说明。格式：[{"symbol":"000001.SZ","action":"持有","reason":"理由"}, ...]
action 必须为：加仓、减仓、清仓、持有 之一。
"""
            api_url = api_url.rstrip("/")
            if not api_url.endswith("/v1/chat/completions"):
                api_url = f"{api_url.rstrip('/')}/v1/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "你是一位专业股票顾问。只输出要求的JSON数组，不要解释。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 800
            }
            resp = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code != 200:
                logger.debug("批量操作建议 AI 请求非200: %s", resp.status_code)
                return None
            data = resp.json()
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
            if not content:
                return None
            content = content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            parsed = json.loads(content)
            if not isinstance(parsed, list):
                return None
            result = []
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                sym = (item.get("symbol") or "").strip()
                act = (item.get("action") or "持有").strip()
                if act not in ("加仓", "减仓", "清仓", "持有"):
                    act = "持有"
                reason = (item.get("reason") or "").strip() or "—"
                if sym:
                    result.append({"symbol": sym, "action": act, "reason": reason})
            if result:
                logger.info("批量操作建议 AI 返回 %d 条 (请求时间: %s)", len(result), datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            return result if result else None
        except Exception as e:
            logger.debug("批量操作建议 AI 调用失败: %s", e)
            return None
    
    def _build_diagnose_interpret_prompt(
        self,
        ts_code: str,
        name: str,
        trade_date: str,
        advice: str,
        stage: str,
        score: int,
        is_started: bool,
        signals: List[str],
        risks: List[str],
        failed_reasons: List[str],
        indicators: Dict,
        checks: Dict,
        market_data: Dict
    ) -> str:
        """
        构建诊断解读的Prompt
        
        Args:
            ts_code: 股票代码
            name: 股票名称
            trade_date: 交易日期
            advice: 诊断建议
            stage: 阶段
            score: 得分
            is_started: 是否启动
            signals: 通过的信号列表
            risks: 风险列表
            failed_reasons: 失败原因列表
            indicators: 指标数据
            checks: 检查项
            market_data: 市场环境数据
            
        Returns:
            str: Prompt文本
        """
        # 提取指标数据
        price_data = indicators.get('price', {})
        volume_data = indicators.get('volume', {})
        ma_data = indicators.get('ma', {})
        technical_data = indicators.get('technical', {})
        
        prompt = f"""请对以下股票启动诊断结果进行专业解读（200-400字）：

【股票信息】
- 名称：{name}
- 代码：{ts_code}
- 日期：{trade_date}
- 收盘价：{price_data.get('close', 0):.2f}元
- 涨跌幅：{price_data.get('change_pct', 0):+.2f}%

【诊断结果】
- 阶段：{stage}
- 得分：{score}分（满分100分）
- 是否启动：{'✅ 是' if is_started else '❌ 否'}
- 诊断建议：{advice}

【通过的信号】
{'\n'.join(f"- {s}" for s in signals) if signals else "- 无"}

【风险提示】
{'\n'.join(f"- {r}" for r in risks) if risks else "- 无"}

【失败原因】
{'\n'.join(f"- {r}" for r in failed_reasons) if failed_reasons else "- 无"}

【技术指标】
- 均线：MA5={ma_data.get('ma5', 0):.2f}, MA10={ma_data.get('ma10', 0):.2f}, MA20={ma_data.get('ma20', 0):.2f}, MA60={ma_data.get('ma60', 0):.2f}
- RSI14：{technical_data.get('rsi14', 0):.1f}
- KDJ-J值：{technical_data.get('kdj_j', 0):.1f}
- 成交额：{volume_data.get('amount', 0):.2f}亿元
- 换手率：{volume_data.get('turnover_rate', 0):.2f}%
- 量比：{volume_data.get('volume_ratio', 0):.2f}x

【关键检查项】
"""
        
        # 添加检查项
        if 'golden_cross' in checks:
            gc = checks['golden_cross']
            prompt += f"- 金叉：{'✅ 通过' if gc.get('passed') else '❌ 未通过'} - {gc.get('current', 'N/A')}\n"
        
        if 'bullish_alignment' in checks:
            ba = checks['bullish_alignment']
            prompt += f"- 均线多头排列：{'✅ 通过' if ba.get('passed') else '❌ 未通过'} - {ba.get('description', 'N/A')}\n"
        
        if 'breakthrough_90d' in checks or 'breakthrough_120d' in checks:
            bt = checks.get('breakthrough_90d') or checks.get('breakthrough_120d')
            prompt += f"- 突破90日高点：{'✅ 通过' if bt.get('passed') else '❌ 未通过'} - {bt.get('description', 'N/A')}\n"
        
        prompt += f"""
【市场环境】
- 上证指数：{market_data.get('sh_index', 'N/A')}
- 深证指数：{market_data.get('sz_index', 'N/A')}
- 市场情绪：{market_data.get('market_sentiment', 'N/A')}

【解读要求】
1. 综合分析诊断结果，解释为什么股票处于当前阶段
2. 分析通过信号和失败原因，说明股票的优势和不足
3. 结合技术指标和市场环境，评估股票的启动潜力
4. 给出专业的投资建议（如：是否值得关注、关键观察点、风险提示等）
5. 语言专业但易懂，避免过于技术化
6. 控制在200-400字

请直接输出解读内容，不要包含其他说明文字。"""
        
        return prompt
    
    def _clean_interpret_text(self, text: str) -> str:
        """
        清理AI解读文本
        
        Args:
            text: 原始文本
            
        Returns:
            str: 清理后的文本
        """
        # 去除markdown代码块标记
        if '```' in text:
            lines = text.split('\n')
            text = '\n'.join([line for line in lines if not line.strip().startswith('```')])
        
        # 去除多余的换行
        text = '\n'.join([line.strip() for line in text.split('\n') if line.strip()])
        
        return text.strip()
    
    def analyze_stock_single(self, stock: Dict) -> Dict:
        """
        分析单只股票（用于流式返回）
        
        Args:
            stock: 股票数据字典
            
        Returns:
            dict: 分析结果
        """
        try:
            # OpenAI分析
            openai_result = self.analyze_stock_openai(stock)
            
            # Deepseek分析
            deepseek_result = self.analyze_stock_deepseek(stock)
            
            # 合并结果
            analyzed_stock = stock.copy()
            analyzed_stock['AI评分'] = openai_result.get('score', 'N/A')
            analyzed_stock['AI分析'] = openai_result.get('analysis', '待AI分析...')
            analyzed_stock['投资建议'] = openai_result.get('suggestion', '分析中...')
            analyzed_stock['Deepseek评分'] = deepseek_result.get('score', 'N/A')
            analyzed_stock['Deepseek分析'] = deepseek_result.get('analysis', '待AI分析...')
            analyzed_stock['Deepseek建议'] = deepseek_result.get('suggestion', '分析中...')
            
            return analyzed_stock
            
        except Exception as e:
            logger.error(f"❌ 分析股票失败: {stock.get('代码', '未知')}, {e}", exc_info=True)
            # 即使分析失败，也保留原始数据
            analyzed_stock = stock.copy()
            analyzed_stock['AI评分'] = 'N/A'
            analyzed_stock['AI分析'] = '分析失败，请稍后重试'
            analyzed_stock['投资建议'] = '分析中...'
            analyzed_stock['Deepseek评分'] = 'N/A'
            analyzed_stock['Deepseek分析'] = '分析失败'
            return analyzed_stock
    
    def analyze_stocks_batch(self, stocks: List[Dict]) -> List[Dict]:
        """
        批量分析股票（保留用于兼容性）
        
        Args:
            stocks: 股票数据列表
            
        Returns:
            list: 分析结果列表
        """
        results = []
        
        for stock in stocks:
            analyzed_stock = self.analyze_stock_single(stock)
            results.append(analyzed_stock)
        
        return results
    
    def _extract_score_from_text(self, text: str) -> str:
        """从文本中提取评分"""
        if not text:
            return 'N/A'
        
        # 尝试提取数字评分
        score_match = re.search(r'评分[：:]\s*(\d+)', text)
        if score_match:
            return score_match.group(1)
        
        score_match = re.search(r'(\d+)\s*分', text)
        if score_match:
            return score_match.group(1)
        
        score_match = re.search(r'"score":\s*"?(\d+)"?', text)
        if score_match:
            return score_match.group(1)
        
        return 'N/A'
    
    def _extract_suggestion_from_text(self, text: str) -> str:
        """从文本中提取建议"""
        if not text:
            return '请自行判断'
        
        # 尝试提取建议
        if '买入' in text or '建议买入' in text:
            return '买入'
        elif '卖出' in text or '建议卖出' in text:
            return '卖出'
        elif '观望' in text or '建议观望' in text:
            return '观望'
        
        return '请自行判断'
    
    def leader_diagnose(
        self,
        ts_code: str,
        stock_data: Dict,
        sector_data: Optional[Dict] = None,
        comparative_data: Optional[List[Dict]] = None,
        timeout: Optional[float] = None
    ) -> Optional[Dict]:
        """
        龙头诊断（基于多级漏斗框架）
        
        Args:
            ts_code: 股票代码
            stock_data: 股票数据字典（包含价格、技术指标等）
            sector_data: 板块数据（可选，包含板块名称、板块涨幅、板块轮动阶段等）
            comparative_data: 同板块对比数据（可选，包含其他股票的表现）
            timeout: 超时时间（秒），默认8秒
            
        Returns:
            Optional[Dict]: 诊断结果，包含：
                - analysis: 综合分析
                - level1_logic: 第一级（逻辑与基本面驱动）分析
                - level2_market: 第二级（市场与资金选择）分析
                - level3_timing: 第三级（参与时机与风险管理）分析
                - recommendation: 操作建议（包含价格区间、止损、目标等）
                失败返回None
        """
        try:
            if not self.config_manager:
                logger.debug("配置管理器未初始化，跳过龙头诊断")
                return None
            
            # 从配置获取Deepseek配置
            deepseek_config = self.config_manager.get_ai_config("deepseek")
            if not deepseek_config:
                logger.warning("Deepseek配置未找到")
                return None

            enabled = self.config_manager.is_ai_enabled("deepseek")
            logger.info(f"Deepseek服务启用状态: enabled={enabled}, config_enabled={deepseek_config.get('enabled', 'N/A')}")

            if not enabled:
                logger.warning("Deepseek服务未启用")
                return None

            api_url = deepseek_config.get("api_url", "").strip()
            api_key = deepseek_config.get("api_key", "").strip()
            model = deepseek_config.get("model", "deepseek-chat")
            config_timeout = deepseek_config.get("timeout", 60)
            
            # 使用传入的timeout，如果没有则使用配置文件中的timeout
            if timeout is None:
                timeout = float(config_timeout)
            
            if not api_url or not api_key:
                logger.debug("Deepseek API未配置，跳过龙头诊断")
                return None
            
            logger.debug(f"🔍 使用超时设置: {timeout}秒 (配置值: {config_timeout}秒)")
            
            # 记录API key的前几个字符用于调试（不记录完整key）
            api_key_preview = api_key[:10] + "..." if len(api_key) > 10 else api_key
            logger.debug(f"🔍 API Key预览: {api_key_preview}, 长度: {len(api_key)}, 是否以sk-开头: {api_key.startswith('sk-')}")
            
            # 提取股票信息
            stock_name = stock_data.get('name') or stock_data.get('股票名称') or '未知'
            stock_price = stock_data.get('close') or stock_data.get('最新价') or stock_data.get('price', 0)
            stock_pct_chg = stock_data.get('change_pct') or stock_data.get('涨跌幅') or stock_data.get('pct_chg', 0)
            stock_amount = stock_data.get('amount') or stock_data.get('成交额', 0)
            stock_amount_yi = stock_amount / 100000000 if stock_amount > 0 else 0
            
            # 获取板块信息
            sector_name = sector_data.get('name', '未知') if sector_data else self._get_sector_name_for_stock(ts_code)
            sector_pct_chg = sector_data.get('pct_chg', 0) if sector_data else 0
            sector_rotation_stage = sector_data.get('rotation_stage', '未知') if sector_data else '未知'
            
            # 获取市场环境数据
            market_data = self._get_market_environment_data()
            
            # 构建Prompt
            prompt = self._build_leader_diagnose_prompt(
                ts_code=ts_code,
                stock_name=stock_name,
                stock_price=stock_price,
                stock_pct_chg=stock_pct_chg,
                stock_amount_yi=stock_amount_yi,
                stock_data=stock_data,
                sector_name=sector_name,
                sector_pct_chg=sector_pct_chg,
                sector_rotation_stage=sector_rotation_stage,
                comparative_data=comparative_data,
                market_data=market_data
            )
            
            # 调用DeepSeek API
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一位资深的股票分析师，擅长使用多级漏斗框架分析股票龙头地位，提供专业的投资建议和风险管理建议。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.7,
                "max_tokens": 1500  # 龙头诊断需要更详细的输出
            }
            
            logger.info(f"📡 调用DeepSeek API进行龙头诊断: {ts_code} ({stock_name}), URL: {api_url}")
            logger.debug(f"🔍 请求头Authorization: Bearer {api_key[:10]}... (长度: {len(api_key)})")
            
            start_time = time.time()
            try:
                response = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
            except requests.exceptions.ConnectionError as e:
                elapsed_time = time.time() - start_time
                logger.error(f"DeepSeek API连接失败: {e}, URL: {api_url}")
                logger.error(f"   请求耗时: {elapsed_time:.2f}秒, 超时设置: {timeout}秒")
                logger.error(f"   请检查网络连接或API服务是否可用")
                return None
            except requests.exceptions.Timeout as e:
                elapsed_time = time.time() - start_time
                logger.error(f"DeepSeek API连接超时: {e}, URL: {api_url}")
                logger.error(f"   请求耗时: {elapsed_time:.2f}秒, 超时设置: {timeout}秒")
                logger.error(f"   建议：1) 检查网络连接 2) 增加timeout配置 3) 检查API服务状态")
                return None
            except requests.exceptions.ReadTimeout as e:
                elapsed_time = time.time() - start_time
                logger.error(f"DeepSeek API读取超时: {e}, URL: {api_url}")
                logger.error(f"   请求耗时: {elapsed_time:.2f}秒, 超时设置: {timeout}秒")
                logger.error(f"   可能是API响应时间过长，建议增加timeout配置")
                return None
            
            elapsed_time = time.time() - start_time
            if elapsed_time > timeout:
                logger.warning(f"DeepSeek API调用超时（{elapsed_time:.2f}s > {timeout}s）")
                return None
            
            # 检查HTTP状态码
            if response.status_code != 200:
                error_detail = response.text[:500]
                logger.error(f"DeepSeek API返回错误状态码: {response.status_code}, 响应: {error_detail}")
                
                # 尝试解析错误信息
                error_msg = "未知错误"
                try:
                    error_json = response.json()
                    error_msg = error_json.get('error', {}).get('message', '未知错误')
                    error_code = error_json.get('error', {}).get('code', '')
                    logger.error(f"DeepSeek API错误详情: {error_msg} (错误代码: {error_code})")
                    
                    # 根据不同的错误状态码提供不同的提示
                    if response.status_code == 401:
                        logger.error(f"⚠️ API认证失败，请检查：")
                        logger.error(f"   1. API Key是否正确（当前预览: {api_key[:10]}...，长度: {len(api_key)}）")
                        logger.error(f"   2. API Key是否已过期")
                        logger.error(f"   3. API URL是否正确: {api_url}")
                        logger.error(f"   4. 是否需要在API Key前添加/删除'Bearer '前缀")
                    elif response.status_code == 402:
                        logger.error(f"⚠️ 账户余额不足，请检查：")
                        logger.error(f"   1. DeepSeek账户余额是否充足")
                        logger.error(f"   2. 是否需要充值")
                        logger.error(f"   3. 访问 https://platform.deepseek.com 查看账户余额")
                    elif response.status_code == 429:
                        logger.error(f"⚠️ API调用频率超限，请稍后重试")
                    elif response.status_code >= 500:
                        logger.error(f"⚠️ DeepSeek服务端错误，请稍后重试")
                except:
                    logger.error(f"无法解析错误响应: {error_detail}")
                
                return None
            
            # API调用成功（状态码200）
            logger.info(f"✅ DeepSeek API调用成功，状态码: {response.status_code}, 耗时: {elapsed_time:.2f}秒")
            
            try:
                result_data = response.json()
                logger.debug(f"🔍 API响应结构: choices数量={len(result_data.get('choices', []))}, 是否有usage信息={('usage' in result_data)}")
                
                # 记录token使用情况（如果有）
                if 'usage' in result_data:
                    usage = result_data['usage']
                    logger.info(f"📊 Token使用情况: prompt_tokens={usage.get('prompt_tokens', 0)}, completion_tokens={usage.get('completion_tokens', 0)}, total_tokens={usage.get('total_tokens', 0)}")
            except Exception as e:
                logger.error(f"DeepSeek API响应解析失败: {e}, 响应内容: {response.text[:500]}")
                logger.error(f"   响应状态码: {response.status_code}, 响应头: {dict(response.headers)}")
                return None
            
            content = result_data.get('choices', [{}])[0].get('message', {}).get('content', '')
            content_length = len(content) if content else 0
            logger.debug(f"🔍 提取的内容长度: {content_length} 字符")
            
            if not content:
                logger.warning(f"⚠️ DeepSeek API返回空内容，完整响应结构: {list(result_data.keys())}")
                logger.warning(f"   响应数据: {str(result_data)[:500]}")
                return None
            
            logger.info(f"✅ 成功获取AI响应内容，长度: {content_length} 字符")
            
            # 解析结果（尝试提取结构化信息）
            logger.debug(f"🔍 开始解析AI响应内容...")
            parsed_result = self._parse_leader_diagnose_result(content, stock_price)
            
            if parsed_result:
                # 添加token使用信息（用于保存到数据库）
                if 'usage' in result_data:
                    parsed_result['_token_usage'] = {
                        'prompt_tokens': result_data['usage'].get('prompt_tokens', 0),
                        'completion_tokens': result_data['usage'].get('completion_tokens', 0),
                        'total_tokens': result_data['usage'].get('total_tokens', 0)
                    }
                
                logger.info(f"✅ DeepSeek龙头诊断完成: {ts_code}, 耗时: {elapsed_time:.2f}s")
                logger.debug(f"🔍 解析结果包含字段: {list(parsed_result.keys())}")
                return parsed_result
            else:
                logger.error(f"❌ 解析结果为空，但API调用成功，内容长度: {len(content)} 字符")
                logger.error(f"   内容预览: {content[:200]}...")
                return None
            
        except requests.exceptions.Timeout:
            logger.warning(f"DeepSeek API调用超时（>{timeout}s）")
            return None
        except requests.exceptions.RequestException as e:
            logger.warning(f"DeepSeek API请求失败: {e}")
            return None
        except Exception as e:
            logger.warning(f"DeepSeek龙头诊断失败: {e}", exc_info=True)
            return None
    
    def _build_leader_diagnose_prompt(
        self,
        ts_code: str,
        stock_name: str,
        stock_price: float,
        stock_pct_chg: float,
        stock_amount_yi: float,
        stock_data: Dict,
        sector_name: str,
        sector_pct_chg: float,
        sector_rotation_stage: str,
        comparative_data: Optional[List[Dict]],
        market_data: Dict
    ) -> str:
        """
        构建龙头诊断的Prompt（基于多级漏斗框架）
        """
        # 提取技术指标
        ma5 = stock_data.get('ma5', 0)
        ma10 = stock_data.get('ma10', 0)
        ma20 = stock_data.get('ma20', 0)
        ma60 = stock_data.get('ma60', 0)
        kdj_j = stock_data.get('kdj_j', 0)
        rsi14 = stock_data.get('rsi14', 0)
        volume_ratio = stock_data.get('amount', 0) / stock_data.get('avg_amount_20d', 1) if stock_data.get('avg_amount_20d', 0) > 0 else 0
        
        prompt = f"""请使用多级漏斗框架对以下股票进行龙头诊断分析：

【股票信息】
- 名称：{stock_name}
- 代码：{ts_code}
- 当前价格：{stock_price:.2f}元
- 今日涨跌幅：{stock_pct_chg:+.2f}%
- 成交额：{stock_amount_yi:.2f}亿元

【技术指标】
- 均线：MA5={ma5:.2f}, MA10={ma10:.2f}, MA20={ma20:.2f}, MA60={ma60:.2f}
- KDJ-J值：{kdj_j:.1f}
- RSI14：{rsi14:.1f}
- 量比：{volume_ratio:.2f}x

【板块信息】
- 所属板块：{sector_name}
- 板块涨跌幅：{sector_pct_chg:+.2f}%
- 板块轮动阶段：{sector_rotation_stage}

【市场环境】
- 上证指数：{market_data.get('sh_index', 'N/A')}
- 深证指数：{market_data.get('sz_index', 'N/A')}
- 市场情绪：{market_data.get('market_sentiment', 'N/A')}
"""
        
        # 添加对比数据
        if comparative_data:
            prompt += "\n【同板块对比股票】\n"
            for comp in comparative_data[:5]:  # 最多显示5只
                comp_name = comp.get('name', '未知')
                comp_pct = comp.get('change_pct', 0)
                comp_amount = comp.get('amount', 0) / 100000000 if comp.get('amount', 0) > 0 else 0
                prompt += f"- {comp_name}: 涨跌幅{comp_pct:+.2f}%, 成交额{comp_amount:.2f}亿元\n"
        
        prompt += """
【多级漏斗框架分析要求】

请按照以下三级漏斗进行分析：

**第一级：逻辑与基本面驱动（核心）**
1. 为什么是这个板块涨？（政策、技术、周期、事件）
2. 板块内，谁最受益？（受益程度、业绩弹性、确定性）
3. 该公司的核心竞争优势是什么？（技术壁垒、成本优势、客户绑定）

**第二级：市场与资金选择（量化模型作为初筛）**
1. 谁先启动？（首个涨停或领涨）
2. 谁最抗跌？（板块调整时跌幅最小，率先反弹）
3. 谁带动性最强？（它一涨，整个板块跟风）
4. 谁的成交额与涨幅匹配最好？（量价健康，换手充分而非缩量一字板）

**第三级：参与时机与风险管理**
1. 当前是否处于"已识别为龙头"的高位？（避免顶部陷阱）
2. 是否有良性分歧或回踩机会？（如涨停板开板回封、回踩关键均线/支撑位）
3. 风险控制建议（止损位、仓位建议、目标位）

【输出格式要求】
请按照以下JSON格式输出（如果无法生成JSON，请使用清晰的文本格式）：

{
  "is_leader": true/false,
  "leader_type": "行业龙头/板块龙头/细分龙头/非龙头",
  "leader_reason": "龙头判断理由（50-100字，说明为什么是或不是龙头）",
  "analysis": "综合分析（200-300字）",
  "level1_logic": "第一级分析：逻辑与基本面驱动（150-200字）",
  "level2_market": "第二级分析：市场与资金选择（150-200字）",
  "level3_timing": "第三级分析：参与时机与风险管理（150-200字）",
  "recommendation": {
    "action": "买入/观望/卖出",
    "price_range": "价格区间（如：12.5-13.0元）",
    "stop_loss": "止损位（如：12.0元）",
    "target": "目标位（如：15.0元）",
    "position": "建议仓位（如：20%）",
    "holding_period": "持有周期（如：5-10个交易日）"
  }
}

**重要：请明确判断该股票是否是行业/板块龙头，并说明理由。**
- is_leader: true表示是龙头，false表示不是龙头
- leader_type: 如果是龙头，请说明是"行业龙头"、"板块龙头"还是"细分龙头"；如果不是，请填写"非龙头"
- leader_reason: 简要说明判断理由，例如："是板块龙头，因为该股在板块中涨幅最大、成交额最高，且带动了板块内其他股票上涨"

请直接输出分析结果，不要包含其他说明文字。"""
        
        return prompt
    
    def _parse_leader_diagnose_result(self, content: str, current_price: float) -> Dict:
        """
        解析龙头诊断结果
        
        Args:
            content: LLM返回的原始内容
            current_price: 当前价格（用于验证价格区间）
            
        Returns:
            Dict: 解析后的诊断结果
        """
        # 清理内容
        content = content.strip()
        logger.debug(f"🔍 解析内容，长度: {len(content)} 字符")
        
        # 尝试解析JSON
        try:
            # 尝试提取JSON部分
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                json_str = json_match.group()
                logger.debug(f"🔍 找到JSON结构，长度: {len(json_str)} 字符")
                parsed = json.loads(json_str)
                logger.info(f"✅ 成功解析JSON格式的诊断结果")
                return {
                    'is_leader': parsed.get('is_leader', False),
                    'leader_type': parsed.get('leader_type', '非龙头'),
                    'leader_reason': parsed.get('leader_reason', ''),
                    'analysis': parsed.get('analysis', content[:300]),
                    'level1_logic': parsed.get('level1_logic', ''),
                    'level2_market': parsed.get('level2_market', ''),
                    'level3_timing': parsed.get('level3_timing', ''),
                    'recommendation': parsed.get('recommendation', {}),
                    'raw_content': content
                }
        except Exception as e:
            logger.debug(f"🔍 JSON解析失败: {e}，将使用文本格式返回")
        
        # 如果JSON解析失败，返回原始内容作为综合分析
        logger.info(f"✅ 使用文本格式返回诊断结果（JSON解析失败或未找到JSON结构）")
        return {
            'is_leader': False,
            'leader_type': '非龙头',
            'leader_reason': '无法解析诊断结果，无法判断',
            'analysis': content,
            'level1_logic': '',
            'level2_market': '',
            'level3_timing': '',
            'recommendation': {
                'action': '观望',
                'price_range': f'{current_price * 0.95:.2f}-{current_price * 1.05:.2f}元',
                'stop_loss': f'{current_price * 0.90:.2f}元',
                'target': f'{current_price * 1.15:.2f}元',
                'position': '10%',
                'holding_period': '5-10个交易日'
            },
            'raw_content': content
        }
    
    def _get_sector_name_for_stock(self, ts_code: str) -> str:
        """
        获取股票所属板块名称（简化版）
        """
        try:
            from backend.services.recommendation.reason_generator import RecommendReasonGenerator
            generator = RecommendReasonGenerator()
            return generator._get_sector_name(ts_code)
        except Exception as e:
            logger.debug("获取板块名称失败: %s", e)
            return '未知'

