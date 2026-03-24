"""
分析 trade_date 更新逻辑，找出重复代码
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

def analyze_trade_date_update_logic():
    """分析 trade_date 更新的所有路径"""
    
    print("=" * 80)
    print("trade_date 更新逻辑分析")
    print("=" * 80)
    print()
    
    print("1. 通过 repository.save() 更新的路径：")
    print("   - check_conditions() -> repository.save() -> _update_existing()")
    print("   - check_assist_conditions() -> repository.save() -> _update_existing()")
    print("   - check_risk_conditions() -> repository.save() -> _update_existing()")
    print("   ✅ 保护：_update_existing() 中已修复，只有在 existing.stage != stage 时才更新")
    print()
    
    print("2. 通过直接操作记录对象更新的路径：")
    print("   - _process_check_result() -> _update_record_fields() -> record.trade_date = trade_date")
    print("   - _handle_missing_conditions_result() -> 直接设置 record.trade_date = trade_date")
    print("   ✅ 保护：backfill_history.py 中的检查是必要的（因为不经过 repository.save()）")
    print()
    
    print("3. 检查逻辑分析：")
    print()
    print("   a) _process_check_result() 中的检查（行 664-675）：")
    print("      - 检查 new_stage == candidate.stage")
    print("      - 如果相同，设置 should_update_trade_date_flag = False")
    print("      - 如果不同，调用 _should_update_trade_date()")
    print("      ✅ 必要：因为 _update_record_fields() 直接操作记录对象")
    print()
    
    print("   b) _handle_missing_conditions_result() 中的检查（行 363-367）：")
    print("      - 检查 new_stage == candidate.stage")
    print("      - 如果相同，设置 should_update_trade_date = False")
    print("      - 如果不同，调用 _should_update_trade_date()")
    print("      ✅ 必要：因为直接设置 record.trade_date = trade_date")
    print()
    
    print("   c) _should_update_trade_date() 函数（行 249-264）：")
    print("      - 判断进入新阶段时，是否需要更新 trade_date")
    print("      - 主要用于判断是否是首次进入某个阶段")
    print("      ✅ 必要：用于更细粒度的控制（首次进入阶段时才更新）")
    print()
    
    print("4. 重复代码分析：")
    print()
    print("   ❌ 行 668-675：检查 new_stage == 'golden_cross' and candidate.stage == 'golden_cross'")
    print("      - 这个检查可以简化为 new_stage == candidate.stage（已修复）")
    print()
    
    print("   ✅ 其他检查都是必要的，因为：")
    print("      - repository.save() 的保护只适用于通过 repository.save() 更新的情况")
    print("      - _update_record_fields() 和直接设置 record.trade_date 需要额外的保护")
    print("      - 这些检查还可以避免不必要的调用 check_conditions 等方法（性能优化）")
    print()
    
    print("5. 总结：")
    print("   - candidate_repository.py 的修复：保护了通过 repository.save() 更新的情况")
    print("   - backfill_history.py 中的检查：保护了直接操作记录对象的情况")
    print("   - 两者是互补的，不是重复的")
    print("   - 唯一的重复是行 668-675 的检查，已简化为 new_stage == candidate.stage")

if __name__ == "__main__":
    analyze_trade_date_update_logic()

