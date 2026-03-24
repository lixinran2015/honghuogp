"""
测试 Tushare 行业资金流向接口 moneyflow_ind_ths
用法（在项目根目录）: python -m scripts.tools.test_moneyflow_ths [YYYYMMDD]
不传日期则用 20260213。
"""
import json
import sys
from pathlib import Path

def main():
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    trade_date = (sys.argv[1] if len(sys.argv) > 1 else "20260213").replace("-", "")
    print(f"测试 moneyflow_ind_ths trade_date={trade_date}")

    config_path = project_root / "config.json"
    if not config_path.exists():
        print("未找到 config.json")
        return 1
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    token = config.get("api_sources", {}).get("tushare", {}).get("token")
    if not token:
        print("config.json 中未配置 api_sources.tushare.token")
        return 1

    import tushare as ts
    ts.set_token(token)
    pro = ts.pro_api()

    try:
        df = pro.moneyflow_ind_ths(
            trade_date=trade_date,
            fields="trade_date,ts_code,industry,net_amount"
        )
        if df is None:
            print("返回: None")
            return 0
        if df.empty:
            print("返回: 空 DataFrame（0 条）")
            print("可能原因: 积分不足(需5000)、该日数据未发布、或接口限频")
            return 0
        print(f"返回: {len(df)} 条")
        print(df.head(10).to_string())
        return 0
    except Exception as e:
        print(f"调用异常: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
