#!/usr/bin/env python3
"""
LSTM-MAB 模型进化系统初始化脚本

一键完成：
1. 初始化数据库表
2. 创建模型保存目录
3. 检查依赖

使用方法:
    python backend/scripts/lstm_mab/setup_evolution.py
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

def main():
    print("=" * 60)
    print("🚀 LSTM-MAB 模型进化系统初始化")
    print("=" * 60)

    # 1. 初始化数据库表
    print("\n📊 步骤 1/3: 初始化数据库表...")
    try:
        from init_evolution_tables import init_evolution_tables
        init_evolution_tables()
        print("✅ 数据库表初始化完成")
    except Exception as e:
        print(f"❌ 数据库表初始化失败: {e}")
        return 1

    # 2. 创建模型保存目录
    print("\n📁 步骤 2/3: 创建模型保存目录...")
    model_dir = "backend/models/lstm_mab"
    try:
        os.makedirs(model_dir, exist_ok=True)
        print(f"✅ 模型目录已创建: {model_dir}")
    except Exception as e:
        print(f"❌ 创建模型目录失败: {e}")
        return 1

    # 3. 检查依赖
    print("\n📦 步骤 3/3: 检查依赖...")
    required_packages = ['sklearn', 'joblib', 'scipy']
    missing = []

    for pkg in required_packages:
        try:
            if pkg == 'sklearn':
                __import__('sklearn')
            elif pkg == 'joblib':
                __import__('joblib')
            elif pkg == 'scipy':
                __import__('scipy')
            print(f"  ✅ {pkg}")
        except ImportError:
            missing.append(pkg)
            print(f"  ❌ {pkg} (未安装)")

    if missing:
        print(f"\n⚠️ 缺少依赖包，请运行:")
        print(f"   pip install {' '.join(missing)}")
        return 1

    print("\n" + "=" * 60)
    print("✅ 初始化完成！")
    print("=" * 60)
    print("\n📖 下一步:")
    print("   1. 训练模型: 访问前端 /lstm-mab 页面，点击'开始训练'")
    print("   2. 每日反馈: 运行 python backend/scripts/lstm_mab/daily_feedback.py")
    print("   3. 监控面板: 访问前端 /lstm-mab-evolution 页面")
    print("\n⏰ 建议设置定时任务:")
    print("   # 每日 15:30 执行反馈循环")
    print("   30 15 * * * cd /path/to/project && python backend/scripts/lstm_mab/daily_feedback.py")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
