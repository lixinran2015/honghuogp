# 东方财富股吧人气榜爬虫方案

## 📋 需求分析

### 目标页面
- URL: https://guba.eastmoney.com/rank/
- 数据量: 前100条排名数据

### 需要爬取的字段
1. **当前排名** - 股票在人气榜中的排名位置
2. **排名较昨日变动** - 相比昨天的排名变化（上升/下降/持平）
3. **历史趋势** - 排名趋势图数据
4. **代码** - 股票代码（如：000001.SZ）
5. **股票名称** - 股票简称
6. **相关** - 相关链接或标签
7. **最新价** - 当前股价
8. **涨跌额** - 价格涨跌金额
9. **涨跌幅** - 价格涨跌百分比
10. **新晋粉丝** - 新关注的粉丝数量
11. **铁杆粉丝** - 长期关注的粉丝数量

## 🔍 技术方案

### 方案选择

#### 方案1: 直接HTTP请求（优先尝试）
- **优点**: 速度快，资源消耗小
- **缺点**: 可能遇到反爬虫限制
- **适用**: 页面是静态渲染或API接口

#### 方案2: Selenium + Chrome（备选）
- **优点**: 可以处理JavaScript渲染，绕过大部分反爬虫
- **缺点**: 速度慢，资源消耗大
- **适用**: 页面是动态渲染或需要模拟浏览器行为

### 实施步骤

1. **页面分析**
   - 检查页面是静态还是动态渲染
   - 查看是否有API接口可以直接调用
   - 分析数据加载方式（初始加载/异步加载）

2. **数据提取**
   - 使用BeautifulSoup解析HTML（静态页面）
   - 或使用Selenium执行JavaScript后解析（动态页面）
   - 或直接调用API接口获取JSON数据

3. **数据处理**
   - 清洗和格式化数据
   - 处理缺失值
   - 数据类型转换

4. **数据存储**
   - 设计数据库表结构
   - 实现数据持久化
   - 支持历史数据追踪

## 🗄️ 数据库设计

### 表结构: `fact_guba_popularity_rank`

```sql
CREATE TABLE fact_guba_popularity_rank (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,              -- 数据日期
    rank_position INTEGER NOT NULL,         -- 当前排名
    rank_change INTEGER,                    -- 排名变动（正数=上升，负数=下降，0=持平）
    ts_code VARCHAR(20) NOT NULL,           -- 股票代码
    stock_name VARCHAR(100),                -- 股票名称
    latest_price DECIMAL(10, 2),            -- 最新价
    change_amount DECIMAL(10, 2),           -- 涨跌额
    change_pct DECIMAL(8, 4),               -- 涨跌幅（%）
    new_fans INTEGER,                       -- 新晋粉丝数
    loyal_fans INTEGER,                     -- 铁杆粉丝数
    trend_data JSONB,                       -- 历史趋势数据（JSON格式）
    related_info TEXT,                      -- 相关信息
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(trade_date, ts_code, rank_position)
);

CREATE INDEX idx_guba_rank_date ON fact_guba_popularity_rank(trade_date);
CREATE INDEX idx_guba_rank_code ON fact_guba_popularity_rank(ts_code);
CREATE INDEX idx_guba_rank_position ON fact_guba_popularity_rank(rank_position);
```

### 历史趋势表: `fact_guba_rank_history`

```sql
CREATE TABLE fact_guba_rank_history (
    id SERIAL PRIMARY KEY,
    ts_code VARCHAR(20) NOT NULL,
    trade_date DATE NOT NULL,
    rank_position INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ts_code, trade_date)
);

CREATE INDEX idx_guba_history_code_date ON fact_guba_rank_history(ts_code, trade_date);
```

## 📂 项目结构

```
backend/
├── scripts/
│   └── crawler/
│       ├── __init__.py
│       ├── guba_popularity_crawler.py      # 主爬虫脚本
│       └── guba_popularity_api.py          # API接口封装
├── services/
│   └── crawler/
│       ├── __init__.py
│       └── guba_popularity_service.py      # 爬虫服务层
└── api/
    └── guba_popularity.py                  # API接口（可选）

data_warehouse/
└── models/
    └── guba_popularity_rank.py             # ORM模型
```

## 🔧 实现细节

### 1. 页面分析方法

#### 方法A: 检查网络请求
```bash
# 使用浏览器开发者工具（F12）查看Network标签
# 查找数据请求（可能是JSON API）
```

#### 方法B: 查看页面源码
```bash
# 检查页面HTML是否包含数据
# 或检查是否有JavaScript异步加载数据
```

### 2. 反爬虫策略

#### 请求头设置
```python
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://guba.eastmoney.com/',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
}
```

#### 请求频率控制
```python
import time
import random

def random_delay(min_seconds=1, max_seconds=3):
    """随机延迟，模拟人类行为"""
    delay = random.uniform(min_seconds, max_seconds)
    time.sleep(delay)
```

### 3. 数据提取策略

#### 使用BeautifulSoup（静态页面）
```python
from bs4 import BeautifulSoup
import requests

def parse_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    # 根据实际页面结构提取数据
    rows = soup.find_all('tr', class_='rank-row')
    for row in rows:
        # 提取各字段数据
        pass
```

#### 使用Selenium（动态页面）
```python
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def parse_with_selenium(url):
    driver = webdriver.Chrome()
    driver.get(url)
    # 等待数据加载
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CLASS_NAME, "rank-table"))
    )
    # 提取数据
    pass
```

## 📝 实现步骤

### 阶段1: 页面分析和原型开发
1. ✅ 分析页面结构
2. ✅ 确定数据提取方法
3. ✅ 编写原型脚本测试

### 阶段2: 爬虫实现
1. ✅ 实现数据提取逻辑
2. ✅ 处理异常情况
3. ✅ 添加日志记录

### 阶段3: 数据存储
1. ✅ 创建数据库表
2. ✅ 实现ORM模型
3. ✅ 实现数据保存逻辑

### 阶段4: 服务化
1. ✅ 封装为服务类
2. ✅ 添加API接口（可选）
3. ✅ 添加定时任务支持

### 阶段5: 测试和优化
1. ✅ 单元测试
2. ✅ 性能优化
3. ✅ 错误处理完善

## 🚨 注意事项

1. **合规性**
   - 遵守网站robots.txt规则
   - 控制请求频率，避免对服务器造成压力
   - 仅用于个人学习和研究

2. **稳定性**
   - 添加重试机制
   - 处理网络超时
   - 处理页面结构变化

3. **数据质量**
   - 数据验证和清洗
   - 处理缺失值
   - 数据去重

4. **维护性**
   - 代码注释清晰
   - 错误日志详细
   - 支持断点续传

## 📊 预期成果

- ✅ 可稳定爬取前100条排名数据
- ✅ 数据自动保存到数据库
- ✅ 支持历史数据追踪
- ✅ 提供API接口查询数据（可选）
- ✅ 支持定时自动更新

## 🔄 后续扩展

1. **数据可视化**
   - 排名趋势图表
   - 粉丝增长趋势

2. **数据分析**
   - 排名变动分析
   - 热门股票识别

3. **预警功能**
   - 排名快速上升提醒
   - 粉丝快速增长提醒

