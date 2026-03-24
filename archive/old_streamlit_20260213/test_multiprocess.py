"""
简单测试脚本：验证多进程是否正常工作
"""
from multiprocessing import Pool, cpu_count, freeze_support, set_start_method
import time

def simple_task(x):
    """简单的测试任务"""
    time.sleep(0.1)  # 模拟工作
    return x * 2

if __name__ == "__main__":
    freeze_support()
    
    try:
        set_start_method('spawn', force=True)
    except RuntimeError:
        pass
    
    print("=" * 50)
    print("🧪 多进程测试脚本")
    print("=" * 50)
    print(f"CPU 核心数: {cpu_count()}")
    
    test_data = list(range(1, 21))  # 测试 20 个任务
    num_processes = min(4, cpu_count())
    
    print(f"进程数: {num_processes}")
    print(f"测试任务数: {len(test_data)}")
    print("\n开始测试...")
    
    start = time.time()
    
    try:
        with Pool(processes=num_processes) as pool:
            results = []
            for i, result in enumerate(pool.imap_unordered(simple_task, test_data, chunksize=2), 1):
                results.append(result)
                print(f"  进度: {i}/{len(test_data)} - 结果: {result}")
        
        elapsed = time.time() - start
        print(f"\n✅ 测试成功！")
        print(f"⏱️  耗时: {elapsed:.2f} 秒")
        print(f"结果: {sorted(results)}")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

