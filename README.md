# 📈 量化交易系统

一个基于 Streamlit 的专业量化交易平台，集成股票分析、策略回测、风险管理等功能，帮助投资者做出更好的交易决策。

![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![Streamlit](https://img.shields.io/badge/streamlit-1.28+-red.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## ✨ 功能特性

### 📊 核心分析功能
- **🔍 股票评估中心**: 单只/批量股票投资价值评估，提供买入价、目标价建议
- **📈 每日策略分析**: 专业市场分析和操作建议  
- **🌊 题材波段交易**: 捕捉热门题材轮动机会
- **📊 涨停板评分**: 多维度评估涨停股票质量
- **🎯 交易信号生成**: 基于技术指标的智能买卖信号
- **🔮 OpenBB分析**: 集成OpenBB平台，提供全球股票、加密货币、经济数据分析

### 🛡️ 风险管理
- **💼 仓位监控**: 实时跟踪持仓状况和盈亏
- **🛡️ 风险评估**: 多维度风险指标分析
- **📋 计划管理**: 系统化交易计划制定和执行
- **🎯 目标达成**: 投资目标跟踪和进度分析

### 🔧 辅助工具
- **📈 策略回测**: 历史数据验证策略有效性
- **😊 市场情绪**: 市场热点和情绪分析
- **⚙️ 系统设置**: 个性化配置和参数调整
- **🌍 全球数据**: 支持美国、中国、香港等多市场数据

## 🚀 快速开始

### 环境要求
- Python 3.8+
- pip 包管理器

### 安装步骤

1. **克隆项目**
```bash
git clone https://github.com/your-username/quantitative_trading.git
cd quantitative_trading
```

2. **创建虚拟环境**（推荐）
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

3. **安装依赖**
```bash
pip install -r requirements.txt
```

4. **验证OpenBB集成**（可选）
```bash
python test_openbb_integration.py
```

5. **启动应用**
```bash
streamlit run app.py
```

6. **访问应用**
打开浏览器访问: http://localhost:8501

## 📖 使用指南

### 股票评估功能
1. 进入 **个股评估** 页面
2. 选择单只或批量评估模式
3. 输入股票代码（如 600519）或名称（如 贵州茅台）
4. 获取详细的投资建议，包括：
   - 现价和涨跌幅
   - 建议买入价
   - 目标价位
   - 止损价位
   - 投资评级（A+ 到 D）
   - 风险等级评估

### 每日策略分析
- 查看当日市场分析
- 获取操作建议
- 关注热点题材
- 风险提示

### 计划管理
- 制定交易计划
- 设置价格提醒
- 跟踪执行情况
- 复盘分析

### OpenBB分析
- **股票分析**: 查看全球股票的历史数据、实时报价、基本面数据
- **加密货币**: 分析比特币、以太坊等加密货币价格走势
- **市场筛选**: 获取活跃股票和涨跌幅排行
- **经济指标**: 查看各国GDP、通胀、失业率等经济数据
- **技术指标**: 计算和可视化SMA、RSI、MACD等技术指标

## 🏗️ 项目架构

```
quantitative_trading/
├── app.py                 # 主应用入口
├── components/            # UI组件
│   ├── sidebar.py        # 侧边栏导航
│   └── data_cache.py     # 数据缓存
├── pages/                 # 页面模块
│   ├── stock_analysis_page.py      # 股票评估
│   ├── daily_strategy_page.py      # 每日策略
│   ├── theme_swing_page.py         # 题材波段
│   ├── plan_management_page.py     # 计划管理
│   └── ...
├── trading_system/        # 交易系统核心
│   ├── data_fetcher.py   # 数据获取
│   └── theme_swing_strategy.py   # 波段策略
├── trading_mission/       # 交易任务
│   ├── market_data.py    # 市场数据
│   ├── trade_executor.py # 交易执行
│   └── trade_review.py   # 交易复盘
├── utils/                 # 工具函数
├── data/                  # 数据存储
└── docs/                  # 文档
```

## 🛠️ 技术栈

- **前端**: Streamlit, Plotly
- **数据处理**: Pandas, NumPy
- **数据源**: AkShare (实时股票数据)
- **可视化**: Plotly, Matplotlib
- **部署**: Docker (可选)

## 📊 数据说明

本系统使用 AkShare 获取真实股票数据，包括：
- 实时股价数据
- 技术指标
- 财务数据
- 市场情绪指标

**注意**: 数据仅供参考，投资决策需谨慎。

## 🤝 贡献指南

欢迎贡献代码！请遵循以下步骤：

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

本项目采用 MIT 许可证。详情请参见 [LICENSE](LICENSE) 文件。

## ⚠️ 免责声明

- 本系统仅供学习和研究使用
- 所有投资建议仅供参考，不构成投资建议
- 投资有风险，入市需谨慎
- 使用本系统进行投资决策的风险由用户自行承担

## 📞 联系方式

如有问题或建议，请通过以下方式联系：

- 📧 邮箱: your-email@example.com
- 🐛 问题反馈: [GitHub Issues](https://github.com/your-username/quantitative_trading/issues)

---

⭐ 如果这个项目对您有帮助，请给我们一个 Star！ 