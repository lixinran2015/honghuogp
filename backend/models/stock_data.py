"""
统一的股票数据模型
用于数据层、策略层、业务层之间的数据传递
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import pandas as pd
import logging

logger = logging.getLogger(__name__)


@dataclass
class StockData:
    """统一的股票数据模型"""
    
    # 基本信息
    code: str  # 股票代码（6位数字，不含前缀）
    name: str  # 股票名称
    
    # 价格数据
    currentPrice: float = 0.0  # 当前价
    open: float = 0.0  # 开盘价
    high: float = 0.0  # 最高价
    low: float = 0.0  # 最低价
    preClose: float = 0.0  # 昨收价
    
    # 涨跌数据
    changePct: float = 0.0  # 涨跌幅（%）
    changeAmount: float = 0.0  # 涨跌额
    
    # 成交数据
    volume: float = 0.0  # 成交量（手）
    amount: float = 0.0  # 成交额（元）
    turnoverRate: float = 0.0  # 换手率（%）
    avgVolume5: float = 0.0  # 5日均量（手）
    
    # 板块信息
    sector: str = "未知"  # 所属行业/板块
    
    # 技术指标（可选）
    ma5: Optional[float] = None
    ma10: Optional[float] = None
    ma20: Optional[float] = None
    ma60: Optional[float] = None
    
    # 扩展字段（用于存储额外信息）
    extra: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StockData':
        """
        从字典创建StockData对象
        
        Args:
            data: 包含股票数据的字典
            
        Returns:
            StockData对象
        """
        # 字段名映射（兼容中英文字段名）
        field_mapping = {
            # 代码
            'code': ['code', '代码', 'ts_code'],
            'name': ['name', '股票名称', '名称', '股票名'],
            # 价格
            'currentPrice': ['currentPrice', 'current_price', '最新价', '当前价', 'lastPrice', 'close'],
            'open': ['open', '开盘', '开盘价'],
            'high': ['high', '最高', '最高价'],
            'low': ['low', '最低', '最低价'],
            'preClose': ['preClose', 'pre_close', 'preClose', '昨收', '昨收价'],
            # 涨跌
            'changePct': ['changePct', 'change_pct', 'pct_chg', '涨跌幅', '涨幅'],
            'changeAmount': ['changeAmount', 'change_amount', '涨跌额'],
            # 成交
            'volume': ['volume', 'vol', '成交量'],
            'amount': ['amount', '成交额'],
            'turnoverRate': ['turnoverRate', 'turnover_rate', '换手率'],
            'avgVolume5': ['avgVolume5', 'avg_volume_5', '5日均量'],
            # 板块
            'sector': ['sector', '行业', '所属行业', '板块', '概念'],
            # 技术指标
            'ma5': ['ma5', 'MA5'],
            'ma10': ['ma10', 'MA10'],
            'ma20': ['ma20', 'MA20'],
            'ma60': ['ma60', 'MA60'],
        }
        
        def get_value(key: str, default: Any = None) -> Any:
            """从字典中获取值，支持多个字段名"""
            if key in field_mapping:
                for field_name in field_mapping[key]:
                    if field_name in data:
                        value = data[field_name]
                        # 处理百分比字段（如果已经是百分比，需要转换）
                        if key == 'changePct' and isinstance(value, str) and value.endswith('%'):
                            return float(value.replace('%', ''))
                        if key == 'turnoverRate' and isinstance(value, str) and value.endswith('%'):
                            return float(value.replace('%', ''))
                        # 处理数值字段
                        try:
                            if key in ['currentPrice', 'open', 'high', 'low', 'preClose', 
                                      'changePct', 'changeAmount', 'volume', 'amount', 
                                      'turnoverRate', 'avgVolume5', 'ma5', 'ma10', 'ma20', 'ma60']:
                                return float(value) if value is not None else default
                            return value if value is not None else default
                        except (ValueError, TypeError):
                            return default
            return default
        
        # 清理代码格式（移除sh/sz/bj前缀）
        code_raw = get_value('code', '')
        if isinstance(code_raw, str):
            code_clean = code_raw.replace('sh', '').replace('sz', '').replace('bj', '').replace('SH', '').replace('SZ', '').replace('BJ', '').replace('.SH', '').replace('.SZ', '').replace('.BJ', '').strip()
        else:
            code_clean = str(code_raw)
        
        # 创建对象
        stock = cls(
            code=code_clean,
            name=get_value('name', ''),
            currentPrice=get_value('currentPrice', 0.0),
            open=get_value('open', 0.0),
            high=get_value('high', 0.0),
            low=get_value('low', 0.0),
            preClose=get_value('preClose', 0.0),
            changePct=get_value('changePct', 0.0),
            changeAmount=get_value('changeAmount', 0.0),
            volume=get_value('volume', 0.0),
            amount=get_value('amount', 0.0),
            turnoverRate=get_value('turnoverRate', 0.0),
            avgVolume5=get_value('avgVolume5', 0.0),
            sector=get_value('sector', '未知'),
            ma5=get_value('ma5'),
            ma10=get_value('ma10'),
            ma20=get_value('ma20'),
            ma60=get_value('ma60'),
        )
        
        # 存储原始数据中的其他字段到extra
        known_fields = set()
        for fields in field_mapping.values():
            known_fields.update(fields)
        for key, value in data.items():
            if key not in known_fields:
                stock.extra[key] = value
        
        return stock
    
    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> list['StockData']:
        """
        从DataFrame批量创建StockData对象列表
        
        Args:
            df: 包含股票数据的DataFrame
            
        Returns:
            StockData对象列表
        """
        stocks = []
        for _, row in df.iterrows():
            try:
                stock_dict = row.to_dict()
                stock = cls.from_dict(stock_dict)
                stocks.append(stock)
            except Exception as e:
                logger.warning(f"从DataFrame创建StockData失败: {e}, row={row.to_dict()}")
                continue
        return stocks
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典（用于JSON序列化）
        
        Returns:
            包含所有字段的字典
        """
        result = {
            'code': self.code,
            'name': self.name,
            'currentPrice': self.currentPrice,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'preClose': self.preClose,
            'changePct': self.changePct,
            'changeAmount': self.changeAmount,
            'volume': self.volume,
            'amount': self.amount,
            'turnoverRate': self.turnoverRate,
            'avgVolume5': self.avgVolume5,
            'sector': self.sector,
        }
        
        # 添加可选字段
        if self.ma5 is not None:
            result['ma5'] = self.ma5
        if self.ma10 is not None:
            result['ma10'] = self.ma10
        if self.ma20 is not None:
            result['ma20'] = self.ma20
        if self.ma60 is not None:
            result['ma60'] = self.ma60
        
        # 添加扩展字段
        if self.extra:
            result.update(self.extra)
        
        return result

