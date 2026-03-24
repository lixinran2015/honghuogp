"""
主线识别配置
"""
# 领先/滞后权重
LEADING_WEIGHT_ALPHA = 0.6
LAGGING_WEIGHT = 1 - LEADING_WEIGHT_ALPHA

# 动量窗口（日）
MOMENTUM_WINDOW = 5

# Top N
MAINLINE_TOP_N = 5
