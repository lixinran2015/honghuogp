"""
检查数据仓库环境配置
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

def check_setup():
    """检查环境配置"""
    print("=" * 60)
    print("数据仓库环境检查")
    print("=" * 60)
    
    # 1. 检查Python依赖
    print("\n1. 检查Python依赖...")
    try:
        import sqlalchemy
        print(f"   ✅ SQLAlchemy: {sqlalchemy.__version__}")
    except ImportError:
        print("   ❌ SQLAlchemy 未安装")
        print("   运行: pip install 'sqlalchemy>=2.0.0'")
    
    try:
        import psycopg2
        print(f"   ✅ psycopg2: {psycopg2.__version__}")
    except ImportError:
        print("   ❌ psycopg2-binary 未安装")
        print("   运行: pip install 'psycopg2-binary>=2.9.0'")
    
    try:
        import tushare
        print(f"   ✅ tushare: {tushare.__version__}")
    except ImportError:
        print("   ⚠️  tushare 未安装（可选，用于财务数据）")
    
    try:
        import akshare
        print(f"   ✅ akshare: {akshare.__version__}")
    except ImportError:
        print("   ⚠️  akshare 未安装（可选，用于行情数据）")
    
    # 2. 检查数据库连接
    print("\n2. 检查数据库连接...")
    from data_warehouse.config import DATABASE_URL
    print(f"   数据库URL: {DATABASE_URL}")
    
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version();"))
            version = result.fetchone()[0]
            print(f"   ✅ PostgreSQL连接成功")
            print(f"   版本: {version.split(',')[0]}")
    except Exception as e:
        print(f"   ❌ PostgreSQL连接失败: {e}")
        print("\n   请先安装并启动PostgreSQL:")
        print("   macOS: brew install postgresql@14")
        print("          brew services start postgresql@14")
        print("          createdb quantitative_trading")
    
    # 3. 检查数据源配置
    print("\n3. 检查数据源配置...")
    from data_warehouse.config import TUSHARE_TOKEN
    if TUSHARE_TOKEN:
        print(f"   ✅ Tushare Token已配置")
    else:
        print("   ⚠️  Tushare Token未配置（从config.json读取）")
    
    # 4. 检查表结构
    print("\n4. 检查数据库表结构...")
    try:
        from sqlalchemy import create_engine, inspect
        engine = create_engine(DATABASE_URL)
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        required_tables = [
            'dim_stock', 'dim_trade_calendar',
            'raw_daily_price', 'raw_fundamental',
            'fact_daily_price', 'fact_fundamental',
            'etl_log'
        ]
        
        missing_tables = [t for t in required_tables if t not in tables]
        
        if not missing_tables:
            print(f"   ✅ 所有表已创建 ({len(tables)} 个表)")
        else:
            print(f"   ⚠️  缺少表: {missing_tables}")
            print("   运行: python -m data_warehouse.db_init")
    except Exception as e:
        print(f"   ❌ 无法检查表结构: {e}")
    
    print("\n" + "=" * 60)
    print("检查完成")
    print("=" * 60)


if __name__ == '__main__':
    check_setup()

