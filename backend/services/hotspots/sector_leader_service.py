"""
板块龙头识别服务
识别板块内的绝对龙头、补涨、跟风股票
"""

import logging
from typing import Dict, List, Optional
from datetime import date
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class SectorLeaderService:
    """板块龙头识别服务"""
    
    def __init__(self):
        """初始化板块龙头识别服务"""
        pass
    
    def identify_sector_leaders(
        self,
        sector_code: str,
        window_start: date,
        window_end: date,
        stock_codes: List[str]
    ) -> List[Dict]:
        """
        识别板块龙头结构
        
        规则：
        1. 绝对龙头：窗口期涨幅最大 + 成交额最大 + 市值较大
        2. 补涨：涨幅次高 + 成交额放大明显
        3. 跟风：其他有涨幅的股票
        
        Args:
            sector_code: 板块编码
            window_start: 窗口开始日期
            window_end: 窗口结束日期
            stock_codes: 板块成分股代码列表
        
        Returns:
            List[Dict]: 龙头列表，每个包含 ts_code, stock_name, leader_type, leader_rank, period_return_pct 等
        """
        try:
            from data_warehouse.service.warehouse_service import WarehouseService
            from data_warehouse.models.generated_models import FactDailyPriceQfq
            from data_warehouse.models.orm_classes import DimStock
            
            warehouse_service = WarehouseService()
            session = warehouse_service.get_session()
            
            try:
                # 1. 获取窗口期内的价格数据（使用前复权价格表）
                prices = session.query(FactDailyPriceQfq).filter(
                    FactDailyPriceQfq.ts_code.in_(stock_codes),
                    FactDailyPriceQfq.trade_date >= window_start,
                    FactDailyPriceQfq.trade_date <= window_end
                ).order_by(FactDailyPriceQfq.ts_code, FactDailyPriceQfq.trade_date).all()
                
                if not prices:
                    logger.warning(f"⚠️ 板块 {sector_code} 没有价格数据")
                    return []
                
                # 2. 按股票代码组织数据
                price_df_data = []
                for p in prices:
                    price_df_data.append({
                        'ts_code': p.ts_code,
                        'trade_date': p.trade_date,
                        'close': float(p.close) if p.close else None,
                        'amount': float(p.amount) if p.amount else 0,
                        'turnover_rate': float(p.turnover_rate) if p.turnover_rate else 0
                    })
                
                price_df = pd.DataFrame(price_df_data)
                
                if price_df.empty:
                    return []
                
                # 3. 计算每只股票的指标
                stock_metrics = []
                
                for ts_code in stock_codes:
                    stock_prices = price_df[price_df['ts_code'] == ts_code].sort_values('trade_date')
                    
                    if stock_prices.empty:
                        continue
                    
                    # 窗口开始和结束价格
                    start_price = stock_prices.iloc[0]['close']
                    end_price = stock_prices.iloc[-1]['close']
                    
                    if not start_price or not end_price or start_price <= 0:
                        continue
                    
                    # 计算涨跌幅
                    period_return_pct = (end_price / start_price - 1) * 100
                    
                    # 计算窗口期成交额总和（亿元）
                    # 过滤掉空值和0值
                    valid_amounts = stock_prices[stock_prices['amount'].notna() & (stock_prices['amount'] > 0)]['amount']
                    if len(valid_amounts) > 0:
                        period_amount = valid_amounts.sum() / 100000000  # 转换为亿元
                    else:
                        period_amount = 0.0
                        logger.warning(f"⚠️ 股票 {ts_code} 窗口期内无有效成交额数据")
                    
                    # 计算平均换手率
                    period_turnover = stock_prices['turnover_rate'].mean()
                    
                    # 获取股票名称（从 DimStock）
                    stock = session.query(DimStock).filter(
                        DimStock.ts_code == ts_code
                    ).first()
                    
                    stock_name = stock.name if stock else ts_code
                    
                    # 获取市值（DimStock 没有市值字段，设为None，不影响龙头识别）
                    market_cap = None
                    # 如果需要市值，可以从 FactDailyPrice 或其他表获取，这里暂时设为None
                    
                    stock_metrics.append({
                        'ts_code': ts_code,
                        'stock_name': stock_name,
                        'period_return_pct': period_return_pct,
                        'period_amount': period_amount,
                        'period_turnover': period_turnover,
                        'market_cap': market_cap
                    })
                
                if not stock_metrics:
                    return []
                
                # 4. 识别龙头类型
                # 按涨幅排序
                stock_metrics.sort(key=lambda x: x['period_return_pct'], reverse=True)
                
                # 绝对龙头：涨幅最大 + 成交额最大 + 市值较大
                absolute_leader = None
                is_sector_declining = False  # 本板块是否全部下跌
                if stock_metrics:
                    # 筛选涨幅 > 0 的股票
                    positive_stocks = [s for s in stock_metrics if s['period_return_pct'] > 0]
                    
                    # 如果没有涨幅 > 0 的股票，选择跌幅最小的（本板块普跌，取相对抗跌代表）
                    if not positive_stocks:
                        is_sector_declining = True
                        logger.warning(f"⚠️ 板块 {sector_code} 本板块普跌，选取跌幅最小（相对抗跌）的代表")
                        positive_stocks = stock_metrics[:3]  # 选择跌幅最小的3只
                    
                    if positive_stocks:
                        # 综合评分：涨幅 * 0.4 + 成交额归一化 * 0.3 + 市值归一化 * 0.3
                        max_amount = max([s['period_amount'] for s in positive_stocks]) if positive_stocks else 1
                        max_cap = max([s['market_cap'] for s in positive_stocks if s['market_cap']]) if any(s['market_cap'] for s in positive_stocks) else 1
                        
                        for stock in positive_stocks:
                            amount_score = (stock['period_amount'] / max_amount) if max_amount > 0 else 0
                            cap_score = (stock['market_cap'] / max_cap) if stock['market_cap'] and max_cap > 0 else 0
                            return_score = stock['period_return_pct'] / 100  # 归一化到0-1
                            
                            stock['leader_score'] = return_score * 0.4 + amount_score * 0.3 + cap_score * 0.3
                            stock['is_sector_declining'] = is_sector_declining
                        
                        # 按综合评分排序
                        positive_stocks.sort(key=lambda x: x.get('leader_score', 0), reverse=True)
                        absolute_leader = positive_stocks[0]
                        # 普跌时用 rel_strength（VARCHAR16），上涨时用 absolute_leader
                        absolute_leader['leader_type'] = 'rel_strength' if is_sector_declining else 'absolute_leader'  # rel_strength≤16字符
                        absolute_leader['leader_rank'] = 1
                
                # 补涨：涨幅次高 + 成交额放大明显（仅当板块有正涨幅股票时）
                catch_up = None
                followers = []
                if not is_sector_declining and absolute_leader and len(positive_stocks) > 1:
                    # 排除绝对龙头，找涨幅次高的
                    remaining = [s for s in positive_stocks if s['ts_code'] != absolute_leader['ts_code']]
                    if remaining:
                        # 找成交额放大最明显的（成交额/涨幅比）
                        for stock in remaining:
                            if stock['period_return_pct'] > 0:
                                stock['catch_up_score'] = stock['period_amount'] / (stock['period_return_pct'] + 1)
                        
                        remaining.sort(key=lambda x: x.get('catch_up_score', 0), reverse=True)
                        catch_up = remaining[0]
                        catch_up['leader_type'] = 'catch_up'
                        catch_up['leader_rank'] = 2
                
                # 跟风：其他有涨幅的股票（仅当板块有正涨幅时）
                leader_codes = set()
                if absolute_leader:
                    leader_codes.add(absolute_leader['ts_code'])
                if catch_up:
                    leader_codes.add(catch_up['ts_code'])
                
                if not is_sector_declining:
                    rank = 3
                    for stock in positive_stocks:
                        if stock['ts_code'] not in leader_codes and stock['period_return_pct'] > 0:
                            stock['leader_type'] = 'follower'
                            stock['leader_rank'] = rank
                            followers.append(stock)
                            rank += 1
                else:
                    # 普跌时：第2、3名标为 resilient（抗跌）
                    rank = 2
                    for stock in positive_stocks[1:3]:
                        if stock['ts_code'] not in leader_codes:
                            stock['leader_type'] = 'resilient'
                            stock['leader_rank'] = rank
                            stock['is_sector_declining'] = True
                            followers.append(stock)
                            rank += 1
                
                # 5. 计算额外的展示指标（1日、5日涨跌幅，涨停天数等）
                from datetime import timedelta
                end_date_1d = window_end
                start_date_1d = window_end - timedelta(days=1)
                end_date_5d = window_end
                start_date_5d = window_end - timedelta(days=5)
                
                def calculate_additional_metrics(leader_dict):
                    ts_code = leader_dict['ts_code']
                    
                    # 获取上一个交易日的数据（最新交易日）
                    latest_price = session.query(FactDailyPriceQfq).filter(
                        FactDailyPriceQfq.ts_code == ts_code,
                        FactDailyPriceQfq.trade_date <= window_end
                    ).order_by(FactDailyPriceQfq.trade_date.desc()).first()
                    
                    # 上一个交易日的价格和成交量
                    last_price = 0.0
                    last_volume = 0.0
                    last_amount = 0.0
                    change_pct_1d = 0.0
                    
                    if latest_price:
                        last_price = float(latest_price.close) if latest_price.close else 0.0
                        last_volume = float(latest_price.vol) if latest_price.vol else 0.0
                        last_amount = float(latest_price.amount) if latest_price.amount else 0.0
                        
                        # 计算1日涨跌幅（如果有前收盘价）
                        if latest_price.pre_close and latest_price.pre_close > 0:
                            change_pct_1d = ((last_price / float(latest_price.pre_close)) - 1) * 100
                        else:
                            # 如果没有前收盘价，获取前一个交易日的数据
                            prev_price = session.query(FactDailyPriceQfq).filter(
                                FactDailyPriceQfq.ts_code == ts_code,
                                FactDailyPriceQfq.trade_date < latest_price.trade_date
                            ).order_by(FactDailyPriceQfq.trade_date.desc()).first()
                            if prev_price and prev_price.close and prev_price.close > 0:
                                change_pct_1d = ((last_price / float(prev_price.close)) - 1) * 100
                    
                    # 5日涨跌幅
                    prices_5d = session.query(FactDailyPriceQfq).filter(
                        FactDailyPriceQfq.ts_code == ts_code,
                        FactDailyPriceQfq.trade_date >= start_date_5d,
                        FactDailyPriceQfq.trade_date <= end_date_5d
                    ).order_by(FactDailyPriceQfq.trade_date).all()
                    
                    change_pct_5d = 0.0
                    if len(prices_5d) >= 2:
                        start_5d = float(prices_5d[0].close) if prices_5d[0].close else None
                        end_5d = float(prices_5d[-1].close) if prices_5d[-1].close else None
                        if start_5d and end_5d and start_5d > 0:
                            change_pct_5d = (end_5d / start_5d - 1) * 100
                    
                    # 涨停天数（简化：检查涨跌幅是否接近10%）
                    limit_up_days = 0
                    max_continuous = 0
                    current_continuous = 0

                    window_prices = price_df[price_df['ts_code'] == ts_code].sort_values('trade_date')
                    if len(window_prices) > 1:
                        prev_close = None
                        for _, row in window_prices.iterrows():
                            if prev_close and prev_close > 0:
                                change_pct = (row['close'] / prev_close - 1) * 100
                                if change_pct >= 9.8:  # 接近涨停
                                    limit_up_days += 1
                                    current_continuous += 1
                                    max_continuous = max(max_continuous, current_continuous)
                                else:
                                    current_continuous = 0
                            prev_close = row['close']

                    # 当前连板数（最新连续涨停天数）
                    current_limit = current_continuous
                    
                    # 量价策略评估
                    volume_price_pattern = None
                    vp_advice = None
                    vp_comment = None
                    
                    if latest_price:
                        try:
                            from backend.strategy.volume_price import classify_volume_price
                            
                            # 准备量价识别所需的数据
                            quote_dict = {
                                'volume': last_volume,  # 成交量（手）
                                'avgVolume5': float(latest_price.avg_volume_5) if latest_price.avg_volume_5 else 0,  # 5日均量
                                'changePct': change_pct_1d,  # 涨跌幅
                                'lastPrice': last_price,  # 当前价格
                                'turnoverRate': float(latest_price.turnover_rate) if latest_price.turnover_rate else 0,  # 换手率
                                'closePrev': float(latest_price.pre_close) if latest_price.pre_close else None,  # 昨收价
                            }
                            
                            pattern, advice, comment = classify_volume_price(quote_dict)
                            volume_price_pattern = pattern
                            vp_advice = advice
                            vp_comment = comment
                        except Exception as e:
                            logger.warning(f"量价识别失败 {ts_code}: {e}")
                    
                    leader_dict['change_pct_1d'] = change_pct_1d
                    leader_dict['change_pct_5d'] = change_pct_5d
                    leader_dict['limit_up_days'] = limit_up_days
                    # 使用当前连板数而不是历史最大连板数，确保主线雷达能正确识别高标龙头
                    leader_dict['continuous_limit'] = current_limit  # 当前连板数（最新连续涨停天数）
                    leader_dict['max_continuous_limit'] = max_continuous  # 历史最大连板数（备用）
                    # 上一个交易日的数据
                    leader_dict['last_price'] = last_price
                    leader_dict['last_volume'] = last_volume  # 成交量（手）
                    leader_dict['last_amount'] = last_amount / 100000000 if last_amount > 0 else 0.0  # 成交额（亿元）
                    # 量价策略评估
                    leader_dict['volume_price_pattern'] = volume_price_pattern
                    leader_dict['vp_advice'] = vp_advice
                    leader_dict['vp_comment'] = vp_comment
                    
                    return leader_dict
                
                # 6. 组装结果并计算额外指标
                leaders = []
                if absolute_leader:
                    calculate_additional_metrics(absolute_leader)
                    leaders.append(absolute_leader)
                if catch_up:
                    calculate_additional_metrics(catch_up)
                    leaders.append(catch_up)
                for follower in followers[:10]:  # 最多10个跟风
                    calculate_additional_metrics(follower)
                    leaders.append(follower)
                
                decl_str = '（本板块普跌，取相对抗跌）' if is_sector_declining else ''
                logger.info(f"✅ 板块 {sector_code} 识别到 {len(leaders)} 个龙头：{'相对抗跌1个' if is_sector_declining else '绝对龙头1个'}，补涨{'1个' if catch_up else '0个'}，{'抗跌' if is_sector_declining else '跟风'}{len(followers)}个{decl_str}")
                
                return leaders
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"❌ 识别板块龙头失败 {sector_code}: {e}", exc_info=True)
            return []

