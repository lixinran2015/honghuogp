"""
交易规则配置
集中管理严格筛选、单日频率、止损与冷却等规则
"""
# 买入筛选
SECTOR_AMOUNT_TOP_N = 5           # 只参与板块成交额前N的个股
MA_BULLISH_REQUIRED = True       # 均线多头排列（MA5>MA10>MA20>MA60）
VOLUME_RATIO_MIN = 1.5           # 量比最低要求
SECTOR_TREND_UP_REQUIRED = True  # 板块日线趋势向上

# 单日交易频率（仅当 bypass_trading_rules=False 时生效；手动添加均为 True，故实际不限制）
MAX_NEW_POSITIONS_PER_DAY = 9   # 每日新开仓上限
LOSS_COOLDOWN_HALF_DAY = True    # 亏损后强制空仓半天（当日不再开新仓）

# 止损与冷却
PROFIT_STOP_DAYS = 3             # 持股N天无盈利无条件离场
SAME_STOCK_COOLDOWN_DAYS = 10    # 同一股N个交易日内不重复操作（约两周）


def get_max_new_positions_per_day() -> int:
    return MAX_NEW_POSITIONS_PER_DAY


def get_same_stock_cooldown_days() -> int:
    return SAME_STOCK_COOLDOWN_DAYS


def get_profit_stop_days() -> int:
    return PROFIT_STOP_DAYS
