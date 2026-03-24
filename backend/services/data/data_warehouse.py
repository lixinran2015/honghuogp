"""
数据仓库服务
用于存储和管理股票数据、财务数据，避免频繁调用外部API
"""

import os
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd

logger = logging.getLogger(__name__)


def _default_warehouse_root() -> Path:
    """数据仓库默认根目录：项目根目录下的 data_warehouse，与 collect_industry_cycle_data 读取路径一致"""
    return Path(__file__).resolve().parents[3] / "data_warehouse"


class DataWarehouse:
    """数据仓库类"""
    
    def __init__(self, base_dir: Optional[str] = None):
        """
        初始化数据仓库
        
        Args:
            base_dir: 数据仓库根目录，None 或 "data_warehouse" 时使用项目根/data_warehouse（与行业周期采集读取路径一致）
        """
        if base_dir is None or base_dir == "data_warehouse":
            self.base_dir = _default_warehouse_root()
        else:
            self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        # 子目录
        self.stocks_dir = self.base_dir / "stocks"  # 股票行情数据
        self.financial_dir = self.base_dir / "financial"  # 财务数据
        self.moneyflow_dir = self.base_dir / "moneyflow"  # 资金流向数据
        self.stocks_dir.mkdir(exist_ok=True)
        self.financial_dir.mkdir(exist_ok=True)
        self.moneyflow_dir.mkdir(exist_ok=True)
        
        logger.info(f"📦 数据仓库初始化: {self.base_dir}")
    
    def get_date_path(self, date: str, data_type: str = "stocks") -> Path:
        """
        获取指定日期的数据文件路径
        
        Args:
            date: 日期，格式：YYYY-MM-DD
            data_type: 数据类型，'stocks' 或 'financial'
        
        Returns:
            Path: 数据文件路径
        """
        if data_type == "stocks":
            return self.stocks_dir / f"{date}.csv"
        elif data_type == "financial":
            return self.financial_dir / f"{date}.json"
        else:
            raise ValueError(f"未知的数据类型: {data_type}")
    
    def save_stocks_data(self, date: str, data: pd.DataFrame) -> bool:
        """
        保存股票行情数据
        
        Args:
            date: 日期，格式：YYYY-MM-DD
            data: 股票数据DataFrame
        
        Returns:
            bool: 是否保存成功
        """
        try:
            file_path = self.get_date_path(date, "stocks")
            data.to_csv(file_path, index=False, encoding='utf-8-sig')
            logger.info(f"✅ 保存股票数据: {file_path} ({len(data)} 只股票)")
            return True
        except Exception as e:
            logger.error(f"❌ 保存股票数据失败: {e}", exc_info=True)
            return False
    
    def load_stocks_data(self, date: str) -> Optional[pd.DataFrame]:
        """
        加载股票行情数据
        
        Args:
            date: 日期，格式：YYYY-MM-DD
        
        Returns:
            DataFrame: 股票数据，如果不存在返回None
        """
        try:
            file_path = self.get_date_path(date, "stocks")
            if file_path.exists():
                df = pd.read_csv(file_path, encoding='utf-8-sig')
                logger.debug(f"📖 加载股票数据: {file_path} ({len(df)} 只股票)")
                
                # 列名映射：中文列名 -> 英文列名（兼容字段）
                column_mapping = {
                    '代码': 'code',
                    '名称': 'name',
                    '最新价': 'lastPrice',
                    '涨跌幅': 'pct_chg',
                    '涨跌额': 'change',
                    '成交额': 'amount',
                    '成交量': 'volume',
                    '换手率': 'turnover_rate',
                    '开盘': 'open',
                    '最高': 'high',
                    '最低': 'low',
                    '昨收': 'pre_close',
                }
                
                # 只重命名存在的列
                existing_mapping = {k: v for k, v in column_mapping.items() if k in df.columns}
                if existing_mapping:
                    df = df.rename(columns=existing_mapping)
                
                # 确保关键字段存在（如果原列名不存在，尝试从其他列名映射）
                if 'code' not in df.columns and '代码' in df.columns:
                    df['code'] = df['代码']
                if 'name' not in df.columns and '名称' in df.columns:
                    df['name'] = df['名称']
                if 'lastPrice' not in df.columns:
                    # 尝试从其他可能的列名获取
                    for col in ['最新价', '当前价', 'price']:
                        if col in df.columns:
                            df['lastPrice'] = df[col]
                            break
                if 'pct_chg' not in df.columns and '涨跌幅' in df.columns:
                    df['pct_chg'] = pd.to_numeric(df['涨跌幅'].astype(str).str.replace('%', ''), errors='coerce')
                if 'amount' not in df.columns and '成交额' in df.columns:
                    df['amount'] = pd.to_numeric(df['成交额'], errors='coerce')
                if 'turnover_rate' not in df.columns and '换手率' in df.columns:
                    df['turnover_rate'] = pd.to_numeric(df['换手率'].astype(str).str.replace('%', ''), errors='coerce')
                
                return df
            else:
                logger.debug(f"⚠️ 股票数据不存在: {file_path}")
                return None
        except Exception as e:
            logger.error(f"❌ 加载股票数据失败: {e}", exc_info=True)
            return None
    
    def save_financial_data(self, date: str, financial_data: Dict[str, Dict]) -> bool:
        """
        保存财务数据
        
        Args:
            date: 日期，格式：YYYY-MM-DD
            financial_data: 财务数据字典，格式：{stock_code: {财务指标...}}
        
        Returns:
            bool: 是否保存成功
        """
        try:
            file_path = self.get_date_path(date, "financial")
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(financial_data, f, ensure_ascii=False, indent=2)
            logger.info(f"✅ 保存财务数据: {file_path} ({len(financial_data)} 只股票)")
            return True
        except Exception as e:
            logger.error(f"❌ 保存财务数据失败: {e}", exc_info=True)
            return False
    
    def load_financial_data(self, date: str) -> Optional[Dict[str, Dict]]:
        """
        加载财务数据
        
        Args:
            date: 日期，格式：YYYY-MM-DD
        
        Returns:
            dict: 财务数据字典，如果不存在返回None
        """
        try:
            file_path = self.get_date_path(date, "financial")
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.debug(f"📖 加载财务数据: {file_path} ({len(data)} 只股票)")
                return data
            else:
                logger.debug(f"⚠️ 财务数据不存在: {file_path}")
                return None
        except Exception as e:
            logger.error(f"❌ 加载财务数据失败: {e}", exc_info=True)
            return None
    
    def save_moneyflow_data(self, date: str, moneyflow_data: Dict) -> bool:
        """
        保存资金流向数据
        
        Args:
            date: 日期，格式：YYYY-MM-DD
            moneyflow_data: 资金流向数据字典
        
        Returns:
            bool: 是否保存成功
        """
        try:
            file_path = self.moneyflow_dir / f"{date}.json"
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(moneyflow_data, f, ensure_ascii=False, indent=2)
            logger.info(f"✅ 保存资金流向数据: {file_path}")
            return True
        except Exception as e:
            logger.error(f"❌ 保存资金流向数据失败: {e}", exc_info=True)
            return False
    
    def load_moneyflow_data(self, date: str) -> Optional[Dict]:
        """
        加载资金流向数据
        
        Args:
            date: 日期，格式：YYYY-MM-DD
        
        Returns:
            dict: 资金流向数据，如果不存在返回None
        """
        try:
            file_path = self.moneyflow_dir / f"{date}.json"
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.debug(f"📖 加载资金流向数据: {file_path}")
                return data
            else:
                logger.debug(f"⚠️ 资金流向数据不存在: {file_path}")
                return None
        except Exception as e:
            logger.error(f"❌ 加载资金流向数据失败: {e}", exc_info=True)
            return None
    
    def get_stock_financial_data(self, stock_code: str, date: Optional[str] = None) -> Optional[Dict]:
        """
        获取单只股票的财务数据
        
        Args:
            stock_code: 股票代码
            date: 日期，格式：YYYY-MM-DD，如果为None则使用最新可用日期
        
        Returns:
            dict: 财务数据，如果不存在返回None
        """
        if date is None:
            # 查找最新可用日期
            date = self.get_latest_financial_date()
            if date is None:
                return None
        
        financial_data = self.load_financial_data(date)
        if financial_data:
            # 标准化股票代码格式
            code_key = self._normalize_code(stock_code)
            return financial_data.get(code_key)
        
        return None
    
    def get_latest_financial_date(self) -> Optional[str]:
        """
        获取最新可用的财务数据日期
        
        Returns:
            str: 最新日期，格式：YYYY-MM-DD，如果没有数据返回None
        """
        if not self.financial_dir.exists():
            return None
        
        dates = []
        for file in self.financial_dir.glob("*.json"):
            date_str = file.stem
            try:
                datetime.strptime(date_str, "%Y-%m-%d")
                dates.append(date_str)
            except ValueError:
                continue
        
        if dates:
            dates.sort(reverse=True)
            return dates[0]
        return None
    
    def get_latest_stocks_date(self) -> Optional[str]:
        """
        获取最新可用的股票数据日期
        
        Returns:
            str: 最新日期，格式：YYYY-MM-DD，如果没有数据返回None
        """
        if not self.stocks_dir.exists():
            return None
        
        dates = []
        for file in self.stocks_dir.glob("*.csv"):
            date_str = file.stem
            try:
                datetime.strptime(date_str, "%Y-%m-%d")
                dates.append(date_str)
            except ValueError:
                continue
        
        if dates:
            dates.sort(reverse=True)
            return dates[0]
        return None
    
    def get_date_range(self, start_date: str, end_date: str) -> List[str]:
        """
        获取日期范围内的所有日期
        
        Args:
            start_date: 开始日期，格式：YYYY-MM-DD
            end_date: 结束日期，格式：YYYY-MM-DD
        
        Returns:
            List[str]: 日期列表
        """
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        
        dates = []
        current = start
        while current <= end:
            # 跳过周末
            if current.weekday() < 5:  # 0-4 是周一到周五
                dates.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)
        
        return dates
    
    def _normalize_code(self, code: str) -> str:
        """
        标准化股票代码格式
        
        Args:
            code: 股票代码（可能是 '000001', 'sh000001', 'sz000001' 等格式）
        
        Returns:
            str: 标准化后的代码（统一为 'sh000001' 或 'sz000001' 格式）
        """
        code = str(code).strip()
        
        # 如果已经是完整格式，直接返回
        if code.startswith('sh') or code.startswith('sz'):
            return code.lower()
        
        # 如果是6位数字，添加前缀
        if code.isdigit() and len(code) == 6:
            if code.startswith('6'):
                return f'sh{code}'
            elif code.startswith('0') or code.startswith('3'):
                return f'sz{code}'
        
        return code
    
    def cleanup_old_data(self, days: int = 365):
        """
        清理旧数据（保留最近N天的数据）
        
        Args:
            days: 保留天数
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            # 清理股票数据
            deleted_stocks = 0
            for file in self.stocks_dir.glob("*.csv"):
                try:
                    file_date = datetime.strptime(file.stem, "%Y-%m-%d")
                    if file_date < cutoff_date:
                        file.unlink()
                        deleted_stocks += 1
                except ValueError:
                    continue
            
            # 清理财务数据
            deleted_financial = 0
            for file in self.financial_dir.glob("*.json"):
                try:
                    file_date = datetime.strptime(file.stem, "%Y-%m-%d")
                    if file_date < cutoff_date:
                        file.unlink()
                        deleted_financial += 1
                except ValueError:
                    continue
            
            logger.info(f"🧹 清理旧数据完成: 删除 {deleted_stocks} 个股票数据文件，{deleted_financial} 个财务数据文件")
            
        except Exception as e:
            logger.error(f"❌ 清理旧数据失败: {e}", exc_info=True)

