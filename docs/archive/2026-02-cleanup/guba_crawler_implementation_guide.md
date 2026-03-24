# 股吧人气榜爬虫实现指南

## 📋 第一步：页面分析

### 1.1 打开浏览器开发者工具
1. 访问 https://guba.eastmoney.com/rank/
2. 按 `F12` 打开开发者工具
3. 查看 **Network** 标签

### 1.2 查找数据来源

#### 方法A: 检查是否有API接口
- 在Network标签中，筛选 `XHR` 或 `Fetch`
- 查看是否有JSON数据请求
- 如果有，直接调用API接口（最简单）

#### 方法B: 检查页面HTML结构
- 在Elements标签中，查找排名数据所在的HTML结构
- 记录关键的选择器（class、id等）

#### 方法C: 检查JavaScript渲染
- 如果数据是JavaScript动态加载的，需要使用Selenium

## 📝 第二步：完善解析逻辑

### 2.1 示例：如果数据在表格中

```python
def parse_html(self, html_content: str) -> List[Dict]:
    """解析HTML内容"""
    soup = BeautifulSoup(html_content, 'html.parser')
    results = []
    
    # 查找排名表格（根据实际页面调整选择器）
    table = soup.find('table', {'class': 'rank-table'})  # 调整class名称
    if not table:
        # 尝试其他选择器
        table = soup.find('table', id='rankTable')
    
    if not table:
        logger.error("未找到排名表格")
        return []
    
    # 获取所有数据行（跳过表头）
    rows = table.find('tbody').find_all('tr')
    
    for row in rows:
        cells = row.find_all('td')
        if len(cells) < 10:
            continue
        
        try:
            data = {
                'rank_position': int(cells[0].text.strip()),
                'rank_change': self._parse_rank_change(cells[1].text.strip()),
                'ts_code': cells[2].text.strip(),
                'stock_name': cells[3].text.strip(),
                'latest_price': float(cells[4].text.strip()),
                'change_amount': float(cells[5].text.strip()),
                'change_pct': float(cells[6].text.strip().rstrip('%')),
                'new_fans': int(cells[7].text.strip()),
                'loyal_fans': int(cells[8].text.strip()),
                'trend_data': self._parse_trend(cells[9]),
                'related_info': cells[10].text.strip() if len(cells) > 10 else '',
            }
            results.append(data)
        except Exception as e:
            logger.warning(f"解析行数据失败: {e}")
            continue
    
    return results
```

### 2.2 示例：如果数据通过API获取

```python
def fetch_api_data(self) -> List[Dict]:
    """直接从API获取数据"""
    api_url = "https://guba.eastmoney.com/api/rank/list"  # 需要确认实际API地址
    
    params = {
        'limit': 100,
        'page': 1,
    }
    
    try:
        response = requests.get(
            api_url,
            headers=self.headers,
            params=params,
            timeout=self.timeout
        )
        response.raise_for_status()
        
        data = response.json()
        # 根据实际API响应格式解析数据
        return self._parse_api_response(data)
    except Exception as e:
        logger.error(f"API请求失败: {e}")
        return []
```

## 🗄️ 第三步：创建数据库模型

### 3.1 创建SQL迁移脚本

创建文件: `data_warehouse/sql/create_guba_popularity_rank.sql`

```sql
-- 创建股吧人气榜表
CREATE TABLE IF NOT EXISTS fact_guba_popularity_rank (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    rank_position INTEGER NOT NULL,
    rank_change INTEGER DEFAULT 0,
    ts_code VARCHAR(20) NOT NULL,
    stock_name VARCHAR(100),
    latest_price DECIMAL(10, 2),
    change_amount DECIMAL(10, 2),
    change_pct DECIMAL(8, 4),
    new_fans INTEGER DEFAULT 0,
    loyal_fans INTEGER DEFAULT 0,
    trend_data JSONB,
    related_info TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(trade_date, ts_code, rank_position)
);

CREATE INDEX IF NOT EXISTS idx_guba_rank_date ON fact_guba_popularity_rank(trade_date);
CREATE INDEX IF NOT EXISTS idx_guba_rank_code ON fact_guba_popularity_rank(ts_code);
CREATE INDEX IF NOT EXISTS idx_guba_rank_position ON fact_guba_popularity_rank(rank_position);

-- 创建历史趋势表
CREATE TABLE IF NOT EXISTS fact_guba_rank_history (
    id SERIAL PRIMARY KEY,
    ts_code VARCHAR(20) NOT NULL,
    trade_date DATE NOT NULL,
    rank_position INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ts_code, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_guba_history_code_date ON fact_guba_rank_history(ts_code, trade_date);
```

### 3.2 创建ORM模型

创建文件: `data_warehouse/models/guba_popularity_rank.py`

```python
from sqlalchemy import Column, Integer, String, DECIMAL, DATE, TIMESTAMP, Text, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class FactGubaPopularityRank(Base):
    """股吧人气榜表"""
    __tablename__ = 'fact_guba_popularity_rank'
    
    id = Column(Integer, primary_key=True)
    trade_date = Column(DATE, nullable=False)
    rank_position = Column(Integer, nullable=False)
    rank_change = Column(Integer, default=0)
    ts_code = Column(String(20), nullable=False)
    stock_name = Column(String(100))
    latest_price = Column(DECIMAL(10, 2))
    change_amount = Column(DECIMAL(10, 2))
    change_pct = Column(DECIMAL(8, 4))
    new_fans = Column(Integer, default=0)
    loyal_fans = Column(Integer, default=0)
    trend_data = Column(JSONB)
    related_info = Column(Text)
    created_at = Column(TIMESTAMP, default=datetime.now)
    updated_at = Column(TIMESTAMP, default=datetime.now, onupdate=datetime.now)
```

## 🔧 第四步：实现数据保存

在 `guba_popularity_crawler.py` 中添加保存方法：

```python
def save_to_database(self, data: List[Dict], trade_date: str = None):
    """保存数据到数据库"""
    from data_warehouse.service.warehouse_service import WarehouseService
    from data_warehouse.models.guba_popularity_rank import FactGubaPopularityRank
    from datetime import datetime as dt
    
    if not trade_date:
        trade_date = dt.now().strftime('%Y-%m-%d')
    
    ws = WarehouseService()
    session = ws.get_session()
    
    try:
        saved_count = 0
        for item in data:
            # 检查是否已存在
            existing = session.query(FactGubaPopularityRank).filter(
                FactGubaPopularityRank.trade_date == dt.strptime(trade_date, '%Y-%m-%d').date(),
                FactGubaPopularityRank.ts_code == item['ts_code'],
                FactGubaPopularityRank.rank_position == item['rank_position']
            ).first()
            
            if existing:
                # 更新现有记录
                for key, value in item.items():
                    setattr(existing, key, value)
                existing.updated_at = dt.now()
            else:
                # 创建新记录
                record = FactGubaPopularityRank(
                    trade_date=dt.strptime(trade_date, '%Y-%m-%d').date(),
                    **item
                )
                session.add(record)
            
            saved_count += 1
        
        session.commit()
        logger.info(f"成功保存 {saved_count} 条数据到数据库")
        return saved_count
        
    except Exception as e:
        session.rollback()
        logger.error(f"保存数据失败: {e}", exc_info=True)
        return 0
    finally:
        session.close()
```

## 🧪 第五步：测试运行

### 5.1 测试脚本

```bash
# 运行爬虫测试
python backend/scripts/crawler/guba_popularity_crawler.py
```

### 5.2 调试步骤

1. **先保存到JSON文件**，检查数据格式
2. **打印HTML片段**，确认选择器正确
3. **逐步完善解析逻辑**
4. **最后保存到数据库**

## 📊 预期数据结构示例

```json
[
    {
        "rank_position": 1,
        "rank_change": 2,
        "ts_code": "000001.SZ",
        "stock_name": "平安银行",
        "latest_price": 12.34,
        "change_amount": 0.56,
        "change_pct": 4.76,
        "new_fans": 1234,
        "loyal_fans": 5678,
        "trend_data": {"data": [...]},
        "related_info": "..."
    }
]
```

## ⚠️ 注意事项

1. **页面结构可能变化**：定期检查选择器是否需要更新
2. **反爬虫机制**：如果被封IP，使用代理或增加延迟
3. **数据验证**：确保数据格式正确再保存
4. **错误处理**：添加完善的异常处理和日志记录

## 🚀 后续优化

1. **定时任务**：添加到数据调度服务
2. **API接口**：提供查询接口
3. **数据可视化**：排名趋势图表
4. **预警功能**：排名快速上升提醒

