#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API调用示例脚本
演示如何调用接口获取指定日期的数据
"""

import requests
from typing import Optional, Dict, Any
from datetime import datetime, date, timedelta


class APIClient:
    """API客户端封装类"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        """
        初始化API客户端
        
        Args:
            base_url: API基础URL
        """
        self.base_url = base_url.rstrip('/')
    
    def _request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        method: str = "GET"
    ) -> Dict:
        """
        发送HTTP请求
        
        Args:
            endpoint: API端点路径
            params: 查询参数
            method: HTTP方法
        
        Returns:
            API响应的JSON数据
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method.upper() == "GET":
                response = requests.get(url, params=params, timeout=30)
            elif method.upper() == "POST":
                response = requests.post(url, params=params, timeout=30)
            else:
                raise ValueError(f"不支持的HTTP方法: {method}")
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ 请求失败: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"   响应内容: {e.response.text}")
            raise
    
    def get_guba_popularity(
        self,
        trade_date: Optional[str] = None,
        limit: int = 100,
        min_rank: Optional[int] = None,
        max_rank: Optional[int] = None
    ) -> Dict:
        """
        获取股吧人气排行榜
        
        Args:
            trade_date: 交易日期，格式YYYY-MM-DD
            limit: 返回数量限制
            min_rank: 最低排名
            max_rank: 最高排名
        
        Returns:
            股吧人气排行榜数据
        """
        params = {"limit": limit}
        if trade_date:
            params["trade_date"] = trade_date
        if min_rank is not None:
            params["min_rank"] = min_rank
        if max_rank is not None:
            params["max_rank"] = max_rank
        
        return self._request("/api/guba/popularity", params=params)
    
    def get_limit_up_volume_shrink(
        self,
        trade_date: Optional[str] = None,
        strategy_type: str = "mainboard_limit_up",
        sort_by: str = "limit_up_date",
        sort_order: str = "desc"
    ) -> Dict:
        """
        获取涨停缩量股票列表
        
        Args:
            trade_date: 查询日期，格式YYYY-MM-DD
            strategy_type: 策略类型
            sort_by: 排序字段
            sort_order: 排序方向
        
        Returns:
            涨停缩量股票列表
        """
        params = {
            "strategy_type": strategy_type,
            "sort_by": sort_by,
            "sort_order": sort_order
        }
        if trade_date:
            params["trade_date"] = trade_date
        
        return self._request("/api/limit-up-volume-shrink/list", params=params)
    
    def get_limit_up_volume_shrink_history(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        strategy_type: str = "mainboard_limit_up",
        limit: int = 1000
    ) -> Dict:
        """
        获取涨停缩量历史数据
        
        Args:
            start_date: 开始日期，格式YYYY-MM-DD
            end_date: 结束日期，格式YYYY-MM-DD
            strategy_type: 策略类型
            limit: 最大返回记录数
        
        Returns:
            历史数据
        """
        params = {
            "strategy_type": strategy_type,
            "limit": limit
        }
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        
        return self._request("/api/limit-up-volume-shrink/history", params=params)
    
    def get_stocks_data(
        self,
        date: Optional[str] = None,
        limit: int = 10000
    ) -> Dict:
        """
        获取数据仓库股票数据
        
        Args:
            date: 日期，格式YYYY-MM-DD
            limit: 返回数量限制
        
        Returns:
            股票数据
        """
        params = {"limit": limit}
        if date:
            params["date"] = date
        
        return self._request("/api/data-warehouse/stocks", params=params)
    
    def get_startup_candidates(
        self,
        trade_date: Optional[str] = None,
        stage: Optional[str] = None,
        min_score: Optional[int] = None
    ) -> Dict:
        """
        获取启动候选股票
        
        Args:
            trade_date: 交易日期，格式YYYY-MM-DD
            stage: 阶段过滤
            min_score: 最低得分
        
        Returns:
            启动候选股票列表
        """
        params = {}
        if trade_date:
            params["trade_date"] = trade_date
        if stage:
            params["stage"] = stage
        if min_score is not None:
            params["min_score"] = min_score
        
        return self._request("/api/startup/candidates", params=params)
    
    def get_recommendations(
        self,
        date: Optional[str] = None,
        type: str = "all",
        limit: int = 5,
        force_refresh: bool = False
    ) -> Dict:
        """
        获取推荐股票
        
        Args:
            date: 日期，格式YYYY-MM-DD
            type: 推荐类型
            limit: 每种类型推荐数量
            force_refresh: 是否强制刷新
        
        Returns:
            推荐股票列表
        """
        params = {
            "type": type,
            "limit": limit,
            "force_refresh": force_refresh
        }
        if date:
            params["date"] = date
        
        return self._request("/api/recommendations", params=params)
    
    def get_monitor_s1_stocks(
        self,
        trade_date: Optional[str] = None
    ) -> Dict:
        """
        获取监控S1股票
        
        Args:
            trade_date: 交易日期，格式YYYY-MM-DD
        
        Returns:
            S1股票列表
        """
        params = {}
        if trade_date:
            params["trade_date"] = trade_date
        
        return self._request("/api/monitor-near5/s1-stocks", params=params)
    
    def get_darwin_stocks(
        self,
        date: Optional[str] = None,
        limit: int = 1000,
        force_refresh: bool = False
    ) -> Dict:
        """
        获取达尔文股票
        
        Args:
            date: 日期，格式YYYY-MM-DD
            limit: 返回数量限制
            force_refresh: 是否强制刷新缓存
        
        Returns:
            达尔文股票列表
        """
        params = {
            "limit": limit,
            "force_refresh": force_refresh
        }
        if date:
            params["date"] = date
        
        return self._request("/api/darwin/stocks", params=params)
    
    def get_backtest_signals(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        min_score: int = 60,
        stage_filter: Optional[str] = None
    ) -> Dict:
        """
        获取回测信号数据
        
        Args:
            start_date: 回测开始日期，格式YYYY-MM-DD
            end_date: 回测结束日期，格式YYYY-MM-DD
            min_score: 最低得分
            stage_filter: 阶段过滤
        
        Returns:
            回测信号数据
        """
        params = {"min_score": min_score}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if stage_filter:
            params["stage_filter"] = stage_filter
        
        return self._request("/api/startup/backtest-signals", params=params)
    
    def get_daily_price(
        self,
        trade_date: Optional[str] = None,
        ts_code: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        qfq: bool = True,
        limit: int = 10000
    ) -> Dict:
        """
        获取日线数据
        
        支持三种查询模式：
        1. 单日查询：提供 trade_date
        2. 单股票日期范围查询：提供 ts_code 和 start_date/end_date
        3. 全市场日期范围查询：提供 start_date/end_date
        
        Args:
            trade_date: 交易日期，格式YYYY-MM-DD（单日查询模式）
            ts_code: 股票代码（可选，用于筛选特定股票）
            start_date: 开始日期，格式YYYY-MM-DD（日期范围查询模式）
            end_date: 结束日期，格式YYYY-MM-DD（日期范围查询模式）
            qfq: 是否使用前复权数据，默认True
            limit: 返回数量限制，默认10000
        
        Returns:
            日线数据
        """
        params = {
            "qfq": qfq,
            "limit": limit
        }
        if trade_date:
            params["trade_date"] = trade_date
        if ts_code:
            params["ts_code"] = ts_code
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        
        return self._request("/api/data-warehouse/daily-price", params=params)


def main():
    """主函数 - 演示如何使用API客户端"""
    
    # 创建API客户端
    client = APIClient(base_url="http://localhost:8000")
    
    # 指定日期（示例：2024-01-15）
    target_date = "2024-01-15"
    
    print("=" * 60)
    print("API调用示例 - 获取指定日期的数据")
    print("=" * 60)
    print(f"目标日期: {target_date}\n")
    
    try:
        # 示例1: 获取股吧人气排行榜
        print("📊 示例1: 获取股吧人气排行榜")
        print("-" * 60)
        result = client.get_guba_popularity(trade_date=target_date, limit=10)
        if result.get("success"):
            print(f"✅ 成功获取 {result.get('count', 0)} 条数据")
            print(f"   交易日期: {result.get('trade_date', 'N/A')}")
            if result.get('data'):
                print(f"   前3条数据:")
                for i, item in enumerate(result['data'][:3], 1):
                    print(f"   {i}. {item.get('stock_name', 'N/A')} - 排名: {item.get('rank_position', 'N/A')}")
        else:
            print(f"❌ 获取失败: {result.get('message', '未知错误')}")
        print()
        
        # 示例2: 获取涨停缩量股票
        print("📈 示例2: 获取涨停缩量股票")
        print("-" * 60)
        result = client.get_limit_up_volume_shrink(trade_date=target_date)
        if result.get("success"):
            print(f"✅ 成功获取 {result.get('count', 0)} 条数据")
            print(f"   交易日期: {result.get('trade_date', 'N/A')}")
            if result.get('data'):
                print(f"   前3条数据:")
                for i, item in enumerate(result['data'][:3], 1):
                    print(f"   {i}. {item.get('ts_code', 'N/A')} - {item.get('stock_name', 'N/A')}")
        else:
            print(f"❌ 获取失败: {result.get('message', '未知错误')}")
        print()
        
        # 示例3: 获取启动候选股票
        print("🚀 示例3: 获取启动候选股票")
        print("-" * 60)
        result = client.get_startup_candidates(
            trade_date=target_date,
            stage="confirmed",
            min_score=50
        )
        if result.get("success"):
            print(f"✅ 成功获取 {result.get('count', 0)} 条数据")
            if result.get('data'):
                print(f"   前3条数据:")
                for i, item in enumerate(result['data'][:3], 1):
                    print(f"   {i}. {item.get('ts_code', 'N/A')} - 得分: {item.get('score', 'N/A')} - 阶段: {item.get('stage', 'N/A')}")
        else:
            print(f"❌ 获取失败: {result.get('message', '未知错误')}")
        print()
        
        # 示例4: 获取日期范围的历史数据
        print("📅 示例4: 获取日期范围的历史数据")
        print("-" * 60)
        start_date = "2024-01-01"
        end_date = "2024-01-15"
        result = client.get_limit_up_volume_shrink_history(
            start_date=start_date,
            end_date=end_date
        )
        if result.get("success"):
            print(f"✅ 成功获取 {result.get('count', 0)} 条数据")
            date_range = result.get('date_range', {})
            print(f"   日期范围: {date_range.get('start_date', 'N/A')} 至 {date_range.get('end_date', 'N/A')}")
        else:
            print(f"❌ 获取失败: {result.get('message', '未知错误')}")
        print()
        
        # 示例5: 获取推荐股票
        print("⭐ 示例5: 获取推荐股票")
        print("-" * 60)
        result = client.get_recommendations(
            date=target_date,
            type="all",
            limit=5
        )
        if result.get("date"):
            print(f"✅ 成功获取推荐数据")
            print(f"   日期: {result.get('date', 'N/A')}")
            data = result.get('data', {})
            for rec_type, stocks in data.items():
                if stocks:
                    print(f"   {rec_type}: {len(stocks)} 只股票")
        else:
            print(f"❌ 获取失败")
        print()
        
        # 示例6: 获取指定日期的日线数据
        print("📊 示例6: 获取指定日期的日线数据")
        print("-" * 60)
        # 6.1 获取指定日期的所有股票日线数据（前10条）
        result = client.get_daily_price(
            trade_date=target_date,
            qfq=True,
            limit=10
        )
        if result.get("success"):
            print(f"✅ 成功获取 {result.get('count', 0)} 条日线数据")
            print(f"   交易日期: {result.get('trade_date', 'N/A')}")
            print(f"   前复权: {result.get('qfq', False)}")
            if result.get('data'):
                print(f"   前3条数据:")
                for i, item in enumerate(result['data'][:3], 1):
                    print(f"   {i}. {item.get('ts_code', 'N/A')} - 收盘价: {item.get('close', 'N/A')}")
        else:
            print(f"❌ 获取失败")
        print()
        
        # 6.2 获取指定股票在日期范围内的日线数据
        print("📈 示例6.2: 获取指定股票的日线数据（日期范围）")
        print("-" * 60)
        result = client.get_daily_price(
            ts_code="600519.SH",
            start_date="2024-01-01",
            end_date="2024-01-15",
            qfq=True,
            limit=20
        )
        if result.get("success"):
            print(f"✅ 成功获取 {result.get('count', 0)} 条日线数据")
            print(f"   股票代码: {result.get('ts_code', 'N/A')}")
            print(f"   日期范围: {result.get('start_date', 'N/A')} 至 {result.get('end_date', 'N/A')}")
            if result.get('data'):
                print(f"   前3条数据:")
                for i, item in enumerate(result['data'][:3], 1):
                    print(f"   {i}. {item.get('trade_date', 'N/A')} - 收盘价: {item.get('close', 'N/A')}, MA5: {item.get('ma5', 'N/A')}")
        else:
            print(f"❌ 获取失败")
        print()
        
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

