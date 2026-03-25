# 短线龙头系统优化方案（最终版）

**版本**: v2.0
**日期**: 2026-03-24
**状态**: 待评审

---

## 一、方案概述

### 1.1 背景

当前短线龙头系统已具备基础功能模块，但存在以下核心问题：
- 各模块独立运行，缺乏统一评分体系
- 买卖点策略不完善（有买点无卖点）
- 板块联动分析薄弱
- 情绪周期判断主观性强
- 缺乏严格的风险控制和模型监控

### 1.2 目标

构建**"多因子评分 + 板块联动 + 精细买卖点 + 情绪周期 + 风控监控"**五位一体的短线龙头系统，实现：
- 信号质量提升（胜率目标>45%，盈亏比>1.5）
- 操作闭环（完整买卖策略）
- 风险可控（最大回撤<-20%）
- 数据驱动（量化验证，持续迭代）

### 1.3 核心原则

1. **整合而非重建**：复用龙头跟踪池和推荐系统，避免重复建设
2. **数据闭环**：跟踪→评分→推荐→验证→优化
3. **渐进升级**：小仓位验证→数据积累→模型优化→逐步放大
4. **风险优先**：严格止损，模型监控，熔断机制

---

## 二、系统架构设计

### 2.1 三层架构

```
┌─────────────────────────────────────────────────────────────┐
│  第一层：龙头跟踪池（基础层）- 已有，强化                     │
│  ├── 职责：发现潜在龙头，持续跟踪                            │
│  ├── 输入：全市场股票                                        │
│  ├── 输出：跟踪池候选（空间龙、刚启动、补涨龙）              │
│  └── 优化：增加多因子入池评分，替代简单阈值                  │
├─────────────────────────────────────────────────────────────┤
│  第二层：统一评分引擎（核心层）- 新增                         │
│  ├── 职责：对跟踪池股票进行多因子量化评分                    │
│  ├── 输入：跟踪池股票 + 实时行情 + 板块数据                  │
│  ├── 输出：综合评分（0-100）+ 评级（S/A/B/C）              │
│  └── 定位：连接跟踪与推荐的桥梁                              │
├─────────────────────────────────────────────────────────────┤
│  第三层：真龙头推荐（应用层）- 已有，升级                     │
│  ├── 职责：基于评分生成可执行的推荐列表                      │
│  ├── 输入：高评分股票（S/A级）                              │
│  ├── 输出：带买卖点的推荐清单 + 仓位建议                     │
│  └── 优化：增加买卖点策略、情绪周期过滤                      │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 数据流设计

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  市场数据    │────▶│  数据清洗    │────▶│  因子计算    │
│  (Tushare)   │     │  (校验/补全) │     │  (4大类因子) │
└──────────────┘     └──────────────┘     └──────┬───────┘
                                                  │
┌──────────────┐     ┌──────────────┐     ┌─────▼───────┐
│  推荐列表    │◀────│  买卖点策略  │◀────│ 统一评分引擎 │
│  (带交易计划)│     │  (止损/止盈) │     │  (0-100分)  │
└──────────────┘     └──────────────┘     └──────┬──────┘
                                                  │
┌──────────────┐     ┌──────────────┐     ┌─────▼───────┐
│  效果跟踪    │────▶│  模型监控    │────▶│  龙头跟踪池  │
│  (绩效归因)  │     │  (健康度)    │     │  (持久化)   │
└──────────────┘     └──────────────┘     └─────────────┘
```

---

## 三、核心模块设计

### 3.1 龙头跟踪池升级

#### 3.1.1 当前问题

入池逻辑简单（涨幅15%-120% + 连板数），缺乏质量评估，存在幸存者偏差。

#### 3.1.2 升级方案

**入池评分模型**：

```python
class EntryScoreCalculator:
    """入池评分计算器"""

    def calculate(self, stock_data) -> Dict:
        """
        多因子入池评分
        """
        scores = {
            'momentum': self._score_momentum(stock_data),      # 动量 25分
            'continuity': self._score_continuity(stock_data),  # 连板 25分
            'sector': self._score_sector(stock_data),          # 板块 25分
            'money_flow': self._score_money_flow(stock_data),  # 资金 25分
        }

        total_score = sum(scores.values())

        return {
            'total_score': total_score,
            'grade': self._get_grade(total_score),  # S:90-100, A:75-89, B:60-74, C:<60
            'breakdown': scores,
            'entry_reason': self._generate_reason(scores)
        }

    def _get_grade(self, score: float) -> str:
        if score >= 90: return 'S'
        if score >= 75: return 'A'
        if score >= 60: return 'B'
        return 'C'
```

**动态入池阈值**：

| 市场环境 | 情绪分 | 入池阈值 | 说明 |
|---------|--------|---------|------|
| 高涨期 | >70 | 75分 | 情绪好，提高门槛选最强 |
| 震荡期 | 40-70 | 65分 | 标准门槛 |
| 低迷期 | 20-40 | 55分 | 降低门槛捕捉反弹 |
| 冰点期 | <20 | 50分 | 放宽至50分，但需控制仓位 |

#### 3.1.3 数据表扩展

```sql
-- fact_leader_tracking_pool 扩展
ALTER TABLE fact_leader_tracking_pool ADD COLUMN score DECIMAL(5,2);  -- 综合评分
ALTER TABLE fact_leader_tracking_pool ADD COLUMN grade VARCHAR(2);     -- 评级 S/A/B/C
ALTER TABLE FACT_LEADER_TRACKING_POOL ADD COLUMN BUY_SIGNAL VARCHAR(50); -- 当前买点信号
ALTER TABLE fact_leader_tracking_pool ADD COLUMN risk_level VARCHAR(10); -- 风险等级 高/中/低
ALTER TABLE fact_leader_tracking_pool ADD COLUMN emotion_cycle VARCHAR(20); -- 入池时情绪周期
ALTER TABLE fact_leader_tracking_pool ADD COLUMN sector_strength DECIMAL(5,2); -- 板块强度
```

#### 3.1.4 幸存者偏差缓解

```python
def track_failed_candidates():
    """
    记录未入池的失败案例，用于后续分析
    """
    failed_cases = {
        'stock_code': '000001.SZ',
        'date': '2026-03-24',
        'reason': 'score_too_low',  # 分数过低/炸板/冲高回落等
        'score_breakdown': {...},
        'subsequent_performance': {...}  # 后续3日表现
    }
    # 存入 fact_leader_tracking_failed 表
```

---

### 3.2 统一评分引擎（核心创新）

#### 3.2.1 设计目标

- 独立于跟踪池和推荐系统，为两者提供一致的评分标准
- 支持实时评分更新（盘中）
- 提供评分归因（为什么给这个分）

#### 3.2.2 多因子模型

**因子定义与权重**（初始权重，后续回测优化）：

| 因子类别 | 权重 | 具体指标 | 计算方式 | 数据来源 |
|---------|------|---------|---------|---------|
| **龙头地位** | 30% | 连板高度、封单比、板块排名 | 连板数×10 + 封单比×20 + 板块排名系数×10 | leader_tracking |
| **技术形态** | 25% | 量价配合、突破有效性、筹码集中度 | 成交量/5日均量 + 价格位置(0-100) + 换手率 | 行情数据 |
| **资金流向** | 25% | 主力净流入占比、大单买入比例 | 主力净流入/成交额 | money_flow |
| **情绪热度** | 20% | 板块涨停家数、市场高度、股吧热度 | 板块涨停数/板块总数 + 连板高度系数 + 热度排名 | sentiment + guba |

**因子相关性控制**：

```python
def check_factor_correlation():
    """
    定期检查因子相关性，避免共线性
    VIF > 5 表示存在共线性问题
    """
    from statsmodels.stats.outliers_influence import variance_inflation_factor

    features = ['leader_score', 'technical_score', 'money_flow_score', 'sentiment_score']
    vif_data = pd.DataFrame()
    vif_data["feature"] = features
    vif_data["VIF"] = [variance_inflation_factor(X.values, i)
                       for i in range(len(features))]

    # 如果VIF>5，考虑合并相关因子或调整权重
    return vif_data
```

#### 3.2.3 评分接口

```python
class UnifiedShortTermScorer:
    """
    统一短线评分引擎
    """

    def __init__(self, warehouse_service):
        self.ws = warehouse_service
        self.weights = self._load_optimized_weights()  # 从回测优化的权重

    def score(self, ts_code: str, trade_date: Optional[date] = None) -> Dict:
        """
        计算股票综合评分

        Returns:
            {
                'ts_code': '000001.SZ',
                'name': '平安银行',
                'total_score': 85.5,
                'grade': 'A',
                'breakdown': {
                    'leader_status': 28.0,  # 30分制
                    'technical': 20.5,       # 25分制
                    'money_flow': 22.0,      # 25分制
                    'sentiment': 15.0        # 20分制
                },
                'signals': {
                    'buy_point': '二板缩量',     # 当前买点信号
                    'buy_point_score': 80,       # 买点质量分
                    'risk_level': '中',          # 风险等级
                    'sector_support': True,      # 是否有板块支撑
                    'sector_name': '金融科技'    # 所属热点板块
                },
                'recommendation': {
                    'action': '重点关注',        # 建议操作
                    'position_size': 15,         # 建议仓位(%)
                    'entry_price': 12.5,         # 建议买入价
                    'stop_loss': 11.9,           # 止损价(-5%)
                    'take_profit_1': 13.75,      # 第一止盈(+10%)
                    'take_profit_2': 14.375      # 第二止盈(+15%)
                },
                'updated_at': '2026-03-24 10:30:00'
            }
        """
        pass

    def batch_score(self, ts_codes: List[str]) -> List[Dict]:
        """批量评分"""
        pass

    def get_top_picks(self, min_grade: str = 'A', limit: int = 10) -> List[Dict]:
        """获取TOP精选"""
        pass
```

#### 3.2.4 权重优化机制

```python
class WeightOptimizer:
    """
    基于历史回测优化因子权重
    """

    def optimize(self, historical_data: pd.DataFrame) -> Dict:
        """
        使用滚动窗口优化权重
        目标：最大化Sharpe Ratio
        约束：各因子权重>10%，总和=100%
        """
        from scipy.optimize import minimize

        def objective(weights):
            portfolio_return = np.sum(historical_data.mean() * weights)
            portfolio_volatility = np.sqrt(np.dot(weights.T, np.dot(historical_data.cov(), weights)))
            sharpe_ratio = portfolio_return / portfolio_volatility
            return -sharpe_ratio  # 最小化负Sharpe = 最大化Sharpe

        constraints = {'type': 'eq', 'fun': lambda w: np.sum(w) - 1}
        bounds = [(0.1, 0.5) for _ in range(4)]  # 每个因子10%-50%

        result = minimize(objective, x0=[0.25]*4, bounds=bounds, constraints=constraints)

        return {
            'leader_status': result.x[0],
            'technical': result.x[1],
            'money_flow': result.x[2],
            'sentiment': result.x[3]
        }
```

---

### 3.3 精细化买卖点策略

#### 3.3.1 买点识别体系

| 买点类型 | 触发条件 | 质量分 | 适用场景 | 风险等级 |
|---------|---------|--------|---------|---------|
| **首板放量** | 涨停+成交量>5日均量2倍+板块启动 | 70 | 新题材首日 | 中 |
| **二板缩量** | 连板+成交量<前日70%+板块前排 | 85 | 龙头确立 | 低 |
| **三板换手** | 3连板+换手20%-40%+板块最强 | 80 | 妖股诞生 | 中 |
| **断板反包** | 断板后次日高开3%+5分钟内上板 | 75 | 强势延续 | 高 |
| **龙头首阴** | 龙头首次收阴+板块仍有多股涨停 | 70 | 核心低吸 | 高 |
| **平台突破** | 横盘5日+放量突破平台上沿 | 65 | 趋势启动 | 中 |

**买点识别代码**：

```python
class BuyPointDetector:
    """买点识别器"""

    def detect(self, stock_data: Dict) -> Optional[Dict]:
        """
        识别当前是否符合某类买点
        """
        checks = [
            self._check_first_limit_up_volume(stock_data),
            self._check_second_limit_up_shrink(stock_data),
            self._check_third_limit_up_turnover(stock_data),
            self._check_break_board_rebound(stock_data),
            self._check_leader_first_yin(stock_data),
            self._check_platform_breakout(stock_data),
        ]

        # 返回质量分最高的买点
        valid_signals = [c for c in checks if c is not None]
        if not valid_signals:
            return None

        return max(valid_signals, key=lambda x: x['score'])

    def _check_second_limit_up_shrink(self, data: Dict) -> Optional[Dict]:
        """
        二板缩量买点检查
        """
        conditions = [
            data['continuous_limit'] == 2,  # 二连板
            data['volume_ratio'] < 0.7,      # 成交量<前日70%
            data['sector_rank'] <= 3,        # 板块排名前3
            data['seal_amount_ratio'] > 0.05  # 封单比>5%
        ]

        if all(conditions):
            return {
                'type': '二板缩量',
                'score': 85,
                'confidence': '高',
                'conditions_met': conditions
            }
        return None
```

#### 3.3.2 卖点策略体系

**A. 机械止损**

```python
STOP_LOSS_RULES = {
    'default': {'trigger': -0.03, 'action': '立即清仓'},  # -3%无条件止损
    'aggressive': {'trigger': -0.05, 'action': '立即清仓'},  # 激进模式-5%
    'conservative': {'trigger': -0.02, 'action': '立即清仓'},  # 保守模式-2%
}
```

**B. 动态止盈**

```python
def calculate_take_profit(entry_price: float, current_price: float) -> Dict:
    """
    动态止盈计算
    """
    profit_pct = (current_price - entry_price) / entry_price

    if profit_pct >= 0.15:
        # 浮盈>15%，回撤-5%止盈（保10%利润）
        return {
            'type': 'trailing_stop',
            'trigger_price': entry_price * 1.10,
            'expected_profit': 0.10,
            'message': '浮盈15%以上，回撤至+10%止盈'
        }
    elif profit_pct >= 0.08:
        # 浮盈>8%，回撤-3%止盈（保5%利润）
        return {
            'type': 'trailing_stop',
            'trigger_price': entry_price * 1.05,
            'expected_profit': 0.05,
            'message': '浮盈8%以上，回撤至+5%止盈'
        }
    elif profit_pct >= 0.03:
        # 浮盈>3%，保本出
        return {
            'type': 'break_even',
            'trigger_price': entry_price * 1.01,
            'expected_profit': 0.01,
            'message': '浮盈3%以上，保本出'
        }

    return None
```

**C. 情绪卖点**

```python
EMOTION_EXIT_SIGNALS = [
    {'name': '板块炸板', 'condition': 'sector_bomb_rate > 0.5', 'action': '减仓50%'},
    {'name': '空间板断板', 'condition': 'leader_broken and no_support', 'action': '清仓'},
    {'name': '跌停激增', 'condition': 'limit_down_count > 10', 'action': '清仓'},
    {'name': '情绪冰点', 'condition': 'emotion_score < 20', 'action': '空仓'},
]
```

**D. 时间卖点**

```python
TIME_EXIT_RULES = {
    'max_holding_days': 3,  # 最长持有3天
    'no_limit_up_exit': {   # 3日内未涨停，主动离场
        'day': 3,
        'action': '收盘清仓',
        'reason': '强度不及预期'
    }
}
```

---

### 3.4 情绪周期定位系统

#### 3.4.1 情绪指标计算

```python
class EmotionIndexCalculator:
    """
    市场情绪指数计算器
    """

    def calculate(self, market_data: Dict) -> Dict:
        """
        计算综合情绪指数
        """
        # 基础指标
        limit_up = market_data['limit_up_count']
        limit_down = market_data['limit_down_count']
        max_limit = market_data['max_continuous_limit']
        bomb_count = market_data['bomb_count']

        # 计算分项指标
        up_down_ratio = limit_up / max(limit_down, 1)  # 涨跌停比
        bomb_rate = bomb_count / max(limit_up + bomb_count, 1)  # 炸板率
        yesterday_premium = market_data['yesterday_limit_up_premium']  # 昨日涨停溢价

        # 综合情绪分 (0-100)
        emotion_score = (
            min(up_down_ratio / 10, 1) * 30 +           # 涨跌停比 30%
            min(max_limit / 10, 1) * 30 +               # 连板高度 30%
            (1 - bomb_rate) * 20 +                      # 封板率 20%
            max(min(yesterday_premium / 5, 1), 0) * 20  # 昨日溢价 20%
        )

        # 定位情绪周期
        cycle = self._locate_cycle(emotion_score, up_down_ratio, bomb_rate)

        return {
            'score': emotion_score,
            'cycle': cycle,
            'indicators': {
                'up_down_ratio': up_down_ratio,
                'max_limit': max_limit,
                'bomb_rate': bomb_rate,
                'yesterday_premium': yesterday_premium
            },
            'suggestion': self._get_suggestion(cycle)
        }

    def _locate_cycle(self, score: float, up_down_ratio: float, bomb_rate: float) -> str:
        """
        定位情绪周期
        """
        if score < 20 or up_down_ratio < 1:
            return '冰点期'
        elif score < 40 or bomb_rate > 0.5:
            return '复苏期'
        elif score < 70:
            return '高涨期'
        else:
            return '退潮期' if bomb_rate > 0.3 else '高涨期'

    def _get_suggestion(self, cycle: str) -> Dict:
        """
        根据情绪周期给出操作建议
        """
        suggestions = {
            '冰点期': {
                'action': '空仓或极小仓位试错',
                'max_position': 10,
                'focus': '新题材首板',
                'avoid': '高位股、老题材'
            },
            '复苏期': {
                'action': '积极试仓新龙头',
                'max_position': 50,
                'focus': '二板确认、空间龙',
                'avoid': '跟风股'
            },
            '高涨期': {
                'action': '重仓主线龙头',
                'max_position': 80,
                'focus': '核心龙头、补涨龙',
                'avoid': '杂毛股'
            },
            '退潮期': {
                'action': '减仓兑现',
                'max_position': 30,
                'focus': '空仓观望',
                'avoid': '中位股、跟风股'
            }
        }
        return suggestions.get(cycle)
```

#### 3.4.2 情绪周期与策略映射

| 情绪周期 | 入池阈值 | 最大仓位 | 推荐买点 | 回避类型 |
|---------|---------|---------|---------|---------|
| 冰点期 | 50分 | 10% | 首板放量（新题材） | 所有高位股 |
| 复苏期 | 60分 | 50% | 二板缩量、三板换手 | 跟风股、老题材 |
| 高涨期 | 75分 | 80% | 龙头分歧低吸、补涨龙 | 杂毛股、非主线 |
| 退潮期 | 80分 | 30% | 空仓或核心龙头 | 中位股、跟风股 |

---

### 3.5 真龙头推荐升级

#### 3.5.1 推荐流程

```python
def generate_recommendations(trade_date: date, emotion_cycle: str) -> List[Dict]:
    """
    生成真龙头推荐列表
    """
    # 步骤1：从跟踪池获取高评分候选
    candidates = leader_pool.get_high_score_stocks(min_score=get_threshold(emotion_cycle))

    # 步骤2：叠加实时条件
    candidates = [
        c for c in candidates
        if not c.is_limit_up and  # 未涨停（可买入）
           c.amount > 100_000_000  # 成交额>1亿（流动性）
    ]

    # 步骤3：识别买点
    for c in candidates:
        c.buy_signal = buy_point_detector.detect(c)

    # 步骤4：过滤无买点信号的股票
    candidates = [c for c in candidates if c.buy_signal is not None]

    # 步骤5：情绪周期过滤
    if emotion_cycle == '冰点期':
        candidates = []  # 空仓
    elif emotion_cycle == '退潮期':
        candidates = [c for c in candidates if c.leader_status == '空间龙']

    # 步骤6：生成交易计划
    recommendations = []
    for c in candidates[:10]:  # TOP10
        rec = {
            'ts_code': c.ts_code,
            'name': c.name,
            'grade': c.grade,
            'score': c.score,
            'buy_signal': c.buy_signal,
            'trade_plan': generate_trade_plan(c),
            'reason': generate_recommendation_reason(c)
        }
        recommendations.append(rec)

    return recommendations

def generate_trade_plan(stock: Dict) -> Dict:
    """
    生成交易计划
    """
    current_price = stock['current_price']

    return {
        'entry_price': round(current_price * 1.01, 2),  # 建议买入价（+1%）
        'stop_loss': round(current_price * 0.97, 2),     # 止损价（-3%）
        'take_profit_1': round(current_price * 1.10, 2), # 第一止盈（+10%）
        'take_profit_2': round(current_price * 1.15, 2), # 第二止盈（+15%）
        'position_size': calculate_position_size(stock), # 建议仓位
        'max_holding_days': 3,                           # 最长持有天数
        'time_exit': '3日未涨停主动离场'
    }
```

#### 3.5.2 仓位管理

```python
def calculate_position_size(stock: Dict, emotion_cycle: str) -> int:
    """
    计算建议仓位(%)
    """
    # 基础仓位
    base_position = {
        'S': 20,  # S级最多20%
        'A': 15,  # A级最多15%
        'B': 10,  # B级最多10%
        'C': 5    # C级最多5%
    }.get(stock['grade'], 10)

    # 情绪周期调整
    cycle_multiplier = {
        '冰点期': 0.2,
        '复苏期': 0.8,
        '高涨期': 1.0,
        '退潮期': 0.3
    }.get(emotion_cycle, 0.5)

    # 买点质量调整
    buy_point_multiplier = stock['buy_signal']['score'] / 100

    # 综合计算
    position = base_position * cycle_multiplier * buy_point_multiplier

    return min(int(position), 25)  # 单票不超过25%
```

---

## 四、模型监控与风控

### 4.1 实时监控指标

```python
class ModelMonitor:
    """
    模型健康度监控
    """

    def __init__(self):
        self.alert_thresholds = {
            'min_win_rate': 0.35,           # 胜率低于35%预警
            'min_profit_factor': 1.0,       # 盈亏比低于1预警
            'max_consecutive_losses': 5,    # 连续亏损5笔预警
            'max_drawdown': -0.20,          # 最大回撤20%预警
            'min_sharpe': 0.5               # Sharpe低于0.5预警
        }

    def check_health(self, recent_trades: List[Dict]) -> Dict:
        """
        检查模型健康度
        """
        alerts = []

        # 1. 胜率检查
        win_rate = self._calc_win_rate(recent_trades)
        if win_rate < self.alert_thresholds['min_win_rate']:
            alerts.append({
                'level': 'warning',
                'metric': 'win_rate',
                'value': win_rate,
                'threshold': self.alert_thresholds['min_win_rate'],
                'message': f'胜率{win_rate:.1%}低于阈值，模型可能失效'
            })

        # 2. 盈亏比检查
        pf = self._calc_profit_factor(recent_trades)
        if pf < self.alert_thresholds['min_profit_factor']:
            alerts.append({
                'level': 'critical',
                'metric': 'profit_factor',
                'value': pf,
                'threshold': self.alert_thresholds['min_profit_factor'],
                'message': f'盈亏比{pf:.2f}低于1，策略亏损中'
            })

        # 3. 连续亏损检查
        consecutive = self._calc_consecutive_losses(recent_trades)
        if consecutive >= self.alert_thresholds['max_consecutive_losses']:
            alerts.append({
                'level': 'critical',
                'metric': 'consecutive_losses',
                'value': consecutive,
                'threshold': self.alert_thresholds['max_consecutive_losses'],
                'message': f'连续{consecutive}笔亏损，建议暂停交易'
            })

        # 4. 最大回撤检查
        drawdown = self._calc_max_drawdown(recent_trades)
        if drawdown < self.alert_thresholds['max_drawdown']:
            alerts.append({
                'level': 'critical',
                'metric': 'max_drawdown',
                'value': drawdown,
                'threshold': self.alert_thresholds['max_drawdown'],
                'message': f'最大回撤{drawdown:.1%}超过阈值'
            })

        # 5. Sharpe检查
        sharpe = self._calc_sharpe(recent_trades)
        if sharpe < self.alert_thresholds['min_sharpe']:
            alerts.append({
                'level': 'warning',
                'metric': 'sharpe_ratio',
                'value': sharpe,
                'threshold': self.alert_thresholds['min_sharpe'],
                'message': f'Sharpe比率{sharpe:.2f}偏低'
            })

        # 6. 市场环境变化检查
        if self._detect_regime_change():
            alerts.append({
                'level': 'warning',
                'metric': 'market_regime',
                'message': '市场环境剧变，模型可能不适用'
            })

        return {
            'healthy': len([a for a in alerts if a['level'] == 'critical']) == 0,
            'alerts': alerts,
            'metrics': {
                'win_rate': win_rate,
                'profit_factor': pf,
                'consecutive_losses': consecutive,
                'max_drawdown': drawdown,
                'sharpe_ratio': sharpe
            }
        }
```

### 4.2 熔断机制

| 触发条件 | 行动 | 恢复条件 |
|---------|------|---------|
| 连续5笔亏损 | 减仓50% | 下一笔盈利 |
| 胜率<30%（近20笔） | 暂停交易1周 | 回测验证后恢复 |
| 最大回撤>-20% | 强制清仓，暂停 | 重新评估模型 |
| 市场状态剧变 | 切换至保守模式 | 新状态稳定 |
| 盈亏比<1.0 | 暂停新信号 | 优化参数后恢复 |

```python
class CircuitBreaker:
    """
    熔断机制
    """

    def check_and_execute(self, health_report: Dict) -> Dict:
        """
        检查并执行熔断
        """
        action = {'type': 'none', 'message': '正常运行'}

        critical_alerts = [a for a in health_report['alerts'] if a['level'] == 'critical']

        if not critical_alerts:
            return action

        # 根据最严重的预警执行熔断
        metric = critical_alerts[0]['metric']

        if metric == 'consecutive_losses':
            action = {
                'type': 'reduce_position',
                'reduce_to': 0.5,
                'message': '连续亏损，减仓50%'
            }
        elif metric == 'profit_factor':
            action = {
                'type': 'pause',
                'duration_days': 7,
                'message': '策略亏损，暂停一周'
            }
        elif metric == 'max_drawdown':
            action = {
                'type': 'liquidate',
                'message': '回撤超限，强制清仓'
            }

        return action
```

---

## 五、回测验证框架

### 5.1 回测设计

```python
class ShortTermBacktest:
    """
    短线策略回测框架
    """

    def __init__(self):
        self.config = {
            'initial_capital': 1_000_000,  # 初始资金100万
            'max_position_per_stock': 0.25,  # 单票最大25%
            'commission_rate': 0.0003,       # 佣金万3
            'stamp_duty': 0.001,             # 印花税千1
            'slippage': 0.005,               # 滑点0.5%
            'min_amount': 100_000_000        # 最小成交额1亿
        }

    def run(self, start_date: date, end_date: date) -> Dict:
        """
        执行回测
        """
        portfolio = Portfolio(self.config['initial_capital'])
        trades = []

        for trade_date in trading_days(start_date, end_date):
            # 1. 获取当日信号
            signals = self.get_signals(trade_date)

            # 2. 处理持仓（检查止损/止盈）
            for pos in portfolio.positions:
                action = self.check_exit(pos, trade_date)
                if action:
                    trade = portfolio.execute_exit(pos, action, trade_date)
                    trades.append(trade)

            # 3. 开新仓
            for signal in signals:
                if portfolio.can_open_position(signal):
                    trade = portfolio.execute_entry(signal, trade_date)
                    trades.append(trade)

            # 4. 记录每日净值
            portfolio.update_nav(trade_date)

        # 计算绩效指标
        return self.calculate_metrics(trades, portfolio)

    def calculate_metrics(self, trades: List[Dict], portfolio: Portfolio) -> Dict:
        """
        计算回测绩效指标
        """
        returns = portfolio.daily_returns

        return {
            'total_return': portfolio.total_return,
            'annualized_return': portfolio.annualized_return,
            'max_drawdown': portfolio.max_drawdown,
            'sharpe_ratio': self._calc_sharpe(returns),
            'sortino_ratio': self._calc_sortino(returns),
            'calmar_ratio': portfolio.annualized_return / abs(portfolio.max_drawdown),
            'win_rate': len([t for t in trades if t['profit'] > 0]) / len(trades),
            'profit_factor': abs(sum([t['profit'] for t in trades if t['profit'] > 0])) /
                           abs(sum([t['profit'] for t in trades if t['profit'] < 0])),
            'avg_holding_days': np.mean([t['holding_days'] for t in trades]),
            'total_trades': len(trades),
            'equity_curve': portfolio.equity_curve
        }
```

### 5.2 基准对比

| 基准 | 说明 | 权重 |
|------|------|------|
| 中证1000 | 小盘风格基准 | 40% |
| 等权首板 | 所有首板股票等权买入 | 40% |
| 涨停指数 | 专门追踪涨停股票 | 20% |

### 5.3 压力测试场景

| 场景 | 时间区间 | 通过标准 |
|------|---------|---------|
| 2022年熊市 | 2022.01-2022.10 | 最大回撤<30%，跑赢中证1000 |
| 2020年疫情 | 2020.02-2020.04 | 快速恢复，3个月内创新高 |
| 2021年震荡 | 2021.02-2021.12 | Sharpe>1.0，胜率>40% |
| 2019年慢牛 | 2019.01-2019.12 | 年化收益>50%，跑赢基准 |

---

## 六、前端展示设计

### 6.1 短线龙头仪表盘

```
┌─────────────────────────────────────────────────────────────┐
│  市场简报                              情绪周期: [高涨期🔥]   │
│  ─────────────────────────────────────────────────────────  │
│  涨停: 85家  跌停: 3家  炸板率: 15%  连板高度: 7板          │
│  昨日涨停溢价: +3.2%  市场状态: 活跃                        │
├─────────────────────────────────────────────────────────────┤
│  TOP精选 (S级)                    操作: [一键导入持仓]       │
│  ─────────────────────────────────────────────────────────  │
│  ┌─────────┬─────────┬─────────┬─────────┬─────────┐       │
│  │ 股票    │ 评分    │ 买点    │ 仓位    │ 操作    │       │
│  ├─────────┼─────────┼─────────┼─────────┼─────────┤       │
│  │ 奥瑞德  │ 92 S    │ 二板缩量│ 20%     │ [查看]  │       │
│  │ 华胜天成│ 88 S    │ 断板反包│ 15%     │ [查看]  │       │
│  │ 法尔胜  │ 85 A    │ 首板放量│ 10%     │ [查看]  │       │
│  └─────────┴─────────┴─────────┴─────────┴─────────┘       │
├─────────────────────────────────────────────────────────────┤
│  龙头梯队图                                                 │
│  ─────────────────────────────────────────────────────────  │
│  7板: [奥瑞德] ← 空间龙                                     │
│  5板: [华胜天成]                                            │
│  3板: [法尔胜] [通裕重工]                                   │
│  2板: [国晟科技] [国恩股份] [xx] [xx]                       │
│  首板: [+12家...]                                           │
├─────────────────────────────────────────────────────────────┤
│  板块热度云图                    我的持仓                   │
│  ─────────────                   ─────────                  │
│  [气泡图]                        奥瑞德  +8.8%  [持有]      │
│                                  华胜天成 -5.3% [止损⚠️]    │
│                                  法尔胜   -5.0% [止损⚠️]    │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 股票详情弹窗

```
┌────────────────────────────────────────┐
│  奥瑞德 (600666)        评分: 92 S级   │
│  ────────────────────────────────────  │
│  最新价: 15.80  +10.02%  涨停          │
│  ────────────────────────────────────  │
│  【因子评分】                          │
│  龙头地位 ████████████████████░░ 28/30 │
│  技术形态 ██████████████████░░░░ 22/25 │
│  资金流向 ████████████████████░░ 23/25 │
│  情绪热度 ████████████████░░░░░░ 19/20 │
│  ────────────────────────────────────  │
│  【买点信号】                          │
│  当前买点: 二板缩量                    │
│  买点质量: 85分 (高)                   │
│  板块支撑: 金融科技 (强度: 85)         │
│  ────────────────────────────────────  │
│  【交易计划】                          │
│  建议买入: 15.90 (+0.6%)               │
│  止损价: 15.35 (-3%)                   │
│  第一止盈: 17.38 (+10%)                │
│  第二止盈: 18.17 (+15%)                │
│  建议仓位: 20%                         │
│  ────────────────────────────────────  │
│  [加入持仓]  [查看K线]  [查看研报]     │
└────────────────────────────────────────┘
```

---

## 七、实施路线图

### 7.1 阶段划分

| 阶段 | 时间 | 目标 | 交付物 |
|------|------|------|--------|
| **Phase 1** | 第1-2周 | 基础升级 | 龙头跟踪池评分、数据表扩展 |
| **Phase 2** | 第3-4周 | 核心引擎 | 统一评分引擎、买卖点识别 |
| **Phase 3** | 第5-6周 | 策略整合 | 情绪周期、推荐升级、风控 |
| **Phase 4** | 第7-8周 | 回测验证 | 回测框架、参数优化、压力测试 |
| **Phase 5** | 第9-10周 | 前端优化 | 仪表盘、实时监控、推送 |
| **Phase 6** | 第11-12周 | 实盘验证 | 小仓位验证、数据积累、迭代优化 |

### 7.2 关键里程碑

```
Week 2: 龙头跟踪池评分上线，数据积累开始
Week 4: 统一评分引擎API可用，内部测试
Week 6: 完整买卖策略上线，模拟盘测试
Week 8: 回测报告完成，参数优化定稿
Week 10: 前端仪表盘上线，用户体验优化
Week 12: 小仓位实盘验证，数据反馈闭环
```

---

## 八、风险评估与应对

### 8.1 主要风险

| 风险 | 概率 | 影响 | 应对措施 |
|------|------|------|---------|
| 样本量不足 | 高 | 统计不显著 | 小仓位验证6个月后再评估 |
| 过拟合 | 中 | 实盘表现差 | 滚动回测、样本外测试、正则化 |
| 市场剧变 | 中 | 模型失效 | 熔断机制、情绪周期快速切换 |
| 数据延迟 | 低 | 信号滞后 | 多数据源备份、实时监控 |
| 流动性风险 | 中 | 无法成交 | 过滤成交额<1亿股票 |

### 8.2 成功标准

| 指标 | 最低标准 | 目标标准 | 优秀标准 |
|------|---------|---------|---------|
| 胜率 | >40% | >45% | >50% |
| 盈亏比 | >1.3 | >1.5 | >2.0 |
| Sharpe | >1.0 | >1.5 | >2.0 |
| 最大回撤 | <-25% | <-20% | <-15% |
| 年化收益 | >30% | >50% | >80% |

---

## 九、附录

### 9.1 数据表设计

```sql
-- 龙头跟踪池扩展
ALTER TABLE fact_leader_tracking_pool
ADD COLUMN score DECIMAL(5,2),
ADD COLUMN grade VARCHAR(2),
ADD COLUMN buy_signal VARCHAR(50),
ADD COLUMN risk_level VARCHAR(10),
ADD COLUMN emotion_cycle VARCHAR(20),
ADD COLUMN sector_strength DECIMAL(5,2),
ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- 信号效果跟踪表（新增）
CREATE TABLE short_term_signal_tracking (
    id SERIAL PRIMARY KEY,
    signal_id VARCHAR(50) UNIQUE,
    ts_code VARCHAR(20),
    signal_date DATE,
    signal_type VARCHAR(20),  -- leader/limit_up/startup
    buy_point_type VARCHAR(50),
    entry_price DECIMAL(10,2),

    -- 后续表现
    day1_high DECIMAL(10,2),
    day1_close DECIMAL(10,2),
    day3_max DECIMAL(10,2),
    day3_close DECIMAL(10,2),
    day5_close DECIMAL(10,2),

    -- 结果标记
    exit_price DECIMAL(10,2),
    exit_date DATE,
    exit_reason VARCHAR(20),  -- stop_loss/take_profit/time_exit
    total_return DECIMAL(5,2),

    max_drawdown DECIMAL(5,2),
    holding_days INTEGER,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 模型监控日志（新增）
CREATE TABLE model_monitor_log (
    id SERIAL PRIMARY KEY,
    check_date DATE,
    win_rate DECIMAL(5,2),
    profit_factor DECIMAL(5,2),
    sharpe_ratio DECIMAL(5,2),
    max_drawdown DECIMAL(5,2),
    emotion_cycle VARCHAR(20),
    alerts JSONB,
    action_taken VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 9.2 API接口清单

| 接口 | 方法 | 说明 |
|------|------|------|
| /api/short-term/unified-score | GET | 统一评分查询 |
| /api/short-term/top-picks | GET | TOP精选推荐 |
| /api/short-term/trade-plan | GET | 交易计划生成 |
| /api/short-term/signals | GET | 实时信号查询 |
| /api/short-term/market-emotion | GET | 市场情绪查询 |
| /api/short-term/backtest | POST | 回测执行 |
| /api/short-term/monitor | GET | 模型健康度 |
| /dashboard/short-term | GET | 仪表盘数据 |

---

## 十、总结

### 10.1 核心创新点

1. **统一评分引擎**：连接跟踪池与推荐系统，提供一致的评价标准
2. **多因子动态权重**：基于回测优化，适应不同市场环境
3. **完整买卖闭环**：从买点识别到止损止盈的全流程策略
4. **情绪周期定位**：客观量化市场情绪，指导仓位管理
5. **模型监控熔断**：实时监控健康度，自动风险控制

### 10.2 预期效果

| 维度 | 当前 | 目标 | 提升 |
|------|------|------|------|
| 胜率 | ~35% | >45% | +10% |
| 盈亏比 | ~1.2 | >1.5 | +25% |
| 最大回撤 | -30% | <-20% | -33% |
| 操作效率 | 低 | 高 | +50% |
| 风险控制 | 弱 | 强 | 显著 |

### 10.3 关键成功因素

1. **数据质量**：确保板块归属、资金流向数据准确及时
2. **严格风控**：机械止损必须执行，熔断机制及时响应
3. **持续迭代**：季度回测复盘，模型参数动态优化
4. **心理建设**：接受45%胜率意味着55%交易亏损的现实

---

**文档状态**: 最终版
**评审人**: ___________
**评审日期**: ___________
**批准人**: ___________
**批准日期**: ___________
