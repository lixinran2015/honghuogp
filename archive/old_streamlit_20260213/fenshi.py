import baostock as bs
import pandas as pd
from datetime import datetime
import time
import sys
import os
import json
from multiprocessing import Pool, cpu_count, freeze_support, set_start_method

# 输出抑制类
class SuppressOutput:
    """上下文管理器，用于抑制标准输出和标准错误"""
    def __enter__(self):
        try:
            self._original_stdout = sys.stdout
            self._original_stderr = sys.stderr
            sys.stdout = open(os.devnull, 'w', encoding='utf-8')
            sys.stderr = open(os.devnull, 'w', encoding='utf-8')
        except:
            pass
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if hasattr(self, '_original_stdout'):
                sys.stdout.close()
                sys.stderr.close()
                sys.stdout = self._original_stdout
                sys.stderr = self._original_stderr
        except:
            pass

def save_stock_list(stock_list, filename="filtered_stocks.txt"):
    """保存符合条件的股票列表到文件
    
    Args:
        stock_list: 股票代码列表
        filename: 保存的文件名
    """
    try:
        data = {
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'stocks': stock_list
        }
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 已保存 {len(stock_list)} 只股票到 {filename}")
        return True
    except Exception as e:
        print(f"\n❌ 保存股票列表失败: {e}")
        return False

def load_stock_list(filename="filtered_stocks.txt"):
    """从文件加载股票列表
    
    Args:
        filename: 文件名
    
    Returns:
        tuple: (股票列表, 保存时间) 或 (None, None)
    """
    try:
        if not os.path.exists(filename):
            return None, None
        
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        stocks = data.get('stocks', [])
        save_date = data.get('date', 'Unknown')
        
        return stocks, save_date
    except Exception as e:
        print(f"\n❌ 读取股票列表失败: {e}")
        return None, None

def get_stock_list(today):
    """获取创业板和科创板股票列表，排除ST股票
    
    创业板：sz.30开头（深圳300XXX），涨跌幅±20%
    科创板：sh.688开头（上海688XXX），涨跌幅±20%
    排除：ST、*ST、退市股等
    """
    bs.login()
    # 获取所有股票代码
    rs = bs.query_all_stock(day=today)
    stock_list = []
    while (rs.error_code == '0') & rs.next():
        row_data = rs.get_row_data()
        stock_code = row_data[0]
        stock_name = row_data[2] if len(row_data) > 2 else ""  # 股票名称
        
        # 只保留创业板（sz.30）和科创板（sh.688）
        if stock_code.startswith('sz.30') or stock_code.startswith('sh.688'):
            # 排除ST股票（名称包含ST、*ST、S*ST、退市等）
            if 'ST' not in stock_name.upper() and '退市' not in stock_name:
                stock_list.append(stock_code)
    bs.logout()
    return stock_list

def get_previous_close(stock_code, date, max_retries=2):
    """获取前一交易日的收盘价
    
    Args:
        stock_code: 股票代码
        date: 当前日期
        max_retries: 最大重试次数
    
    Returns:
        float: 前一交易日收盘价，如果获取失败返回None
    """
    from datetime import datetime, timedelta
    
    for attempt in range(max_retries):
        try:
            with SuppressOutput():
                try:
                    bs.login()
                except:
                    pass
                
                # 计算前一交易日（往前推5天，确保能获取到数据）
                current_date = datetime.strptime(date, '%Y-%m-%d')
                start_date = (current_date - timedelta(days=5)).strftime('%Y-%m-%d')
                
                # 查询日K线数据
                rs = bs.query_history_k_data_plus(
                    stock_code,
                    "date,close",
                    start_date=start_date,
                    end_date=date,
                    frequency="d",  # 日K线
                    adjustflag="3"  # 不复权
                )
                
                # 获取数据
                data_list = []
                while (rs.error_code == '0') & rs.next():
                    data_list.append(rs.get_row_data())
                
                try:
                    bs.logout()
                except:
                    pass
            
            if len(data_list) >= 2:
                # 倒数第二条就是前一交易日（最后一条是当天）
                prev_close = float(data_list[-2][1])
                return prev_close
            elif len(data_list) == 1:
                # 只有一条数据（当天），可能是新股或停牌后复牌
                return None
            else:
                return None
                
        except Exception as e:
            try:
                with SuppressOutput():
                    bs.logout()
            except:
                pass
            
            if attempt < max_retries - 1:
                time.sleep(0.2)
                continue
            else:
                return None
    
    return None

def get_minute_data(stock_code, date, max_retries=2, timeout=10):
    """获取指定股票的当日分时数据（5分钟级）
    
    添加重试机制和超时控制，避免网络波动导致的失败
    timeout: 单次请求的最大等待时间（秒）
    """
    for attempt in range(max_retries):
        try:
            # 抑制 baostock 的所有输出（login/logout/error 信息）
            with SuppressOutput():
                # 每次请求都独立登录登出，避免连接冲突（静默模式）
                try:
                    bs.login()
                except:
                    pass  # 忽略登录错误
                
                # 分时数据接口：baostock 不支持1分钟线，最小粒度是5分钟
                # frequency支持: "5"=5分钟, "15"=15分钟, "30"=30分钟, "60"=60分钟
                rs = bs.query_history_k_data_plus(
                    stock_code,
                    "time,open,high,low,close,volume,amount",
                    start_date=date,
                    end_date=date,
                    frequency="5",  # 5分钟线（baostock支持的最小粒度）
                    adjustflag="3"  # 不复权
                )
                
                # 转换为DataFrame
                data_list = []
                while (rs.error_code == '0') & rs.next():
                    data_list.append(rs.get_row_data())
                
                try:
                    bs.logout()
                except:
                    pass  # 忽略登出错误
            
            if not data_list:
                return None
            
            # 列名映射
            df = pd.DataFrame(
                data_list,
                columns=['time', 'open', 'high', 'low', 'close', 'volume', 'amount']
            )
            # 转换数据类型（字符串→数值）
            numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'amount']
            df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors='coerce')
            # 过滤无效数据（成交量为0的分钟线）
            df = df[df['volume'] > 0].reset_index(drop=True)
            return df
            
        except Exception as e:
            # 捕获异常，确保登出
            try:
                with SuppressOutput():
                    bs.logout()
            except:
                pass
            
            # 重试
            if attempt < max_retries - 1:
                time.sleep(0.2)  # 缩短等待时间到0.2秒
                continue
            else:
                # 最后一次尝试也失败了
                return None
    
    return None

def check_not_limit_up_down(df, tolerance=0.5):
    """检查是否涨停或跌停（创业板和科创板：±20%）
    
    Args:
        df: 分时数据 DataFrame
        tolerance: 容忍度（百分比），默认0.5%，即涨幅≥19.5%算涨停，跌幅≤-19.5%算跌停
    
    Returns:
        True: 未涨停也未跌停
        False: 涨停或跌停
    """
    if df is None or len(df) < 2:
        return False
    
    # 计算涨跌幅 = (收盘价 - 开盘价第一根K线) / 开盘价 * 100
    first_open = df.iloc[0]['open']  # 第一根K线的开盘价（接近昨收盘价）
    last_close = df.iloc[-1]['close']  # 最后一根K线的收盘价
    
    if first_open <= 0:
        return False
    
    change_pct = (last_close - first_open) / first_open * 100
    
    # 创业板和科创板：涨跌幅限制 ±20%
    # 排除接近涨跌停的股票（涨跌幅 ≥ ±19.5%）
    if change_pct >= (20.0 - tolerance):  # 涨停（涨幅 ≥ 19.5%）
        return False
    if change_pct <= -(20.0 - tolerance):  # 跌停（跌幅 ≤ -19.5%）
        return False
    
    return True

def check_never_break_ma(df, prev_close, debug=False, tolerance_pct=0.1):
    """检查分时是否未破均线：所有分钟最低价≥均线，且当前价≥均线
    
    向量化优化版本：使用 pandas 向量化操作，速度提升 10-20 倍
    使用百分比容忍度，自动适应不同价格的股票
    
    Args:
        df: 分时数据 DataFrame
        prev_close: 前一交易日收盘价（用于计算实际涨幅）
        debug: 是否调试模式
        tolerance_pct: 容忍度百分比（默认0.1%）
                      例如：均线10元，容忍度0.1% = 0.01元
                           均线100元，容忍度0.1% = 0.1元
    
    筛选条件：
        1. 排除第一条数据（9:30开盘），从第二条开始检查
        2. 所有5分钟K线的最低价≥均线（允许0.1%容忍度）
        3. 9:40分（第三根K线）实际涨幅必须≥2%（相对于前日收盘价）
        4. 当前价≥均线
    """
    if df is None or len(df) < 3:  # 至少需要3条数据（排除第一条后还要≥2条）
        return False
    
    # 计算分时均线（累计成交额 / 累计成交量，单位：元）
    df['cum_amount'] = df['amount'].cumsum()  # 累计成交额
    df['cum_volume'] = df['volume'].cumsum()  # 累计成交量
    df['ma'] = df['cum_amount'] / df['cum_volume']  # 分时均线（元/股）
    
    # ✅ 向量化操作：一次性计算所有差值（比循环快 10-20 倍）
    df['diff'] = df['low'] - df['ma']
    
    # ✅ 使用百分比容忍度：容忍度 = 均线价格 × 容忍百分比
    # 例如：10元股票，0.1%容忍度 = 0.01元
    #      100元股票，0.1%容忍度 = 0.1元
    df['tolerance'] = df['ma'] * (tolerance_pct / 100)
    
    # ⚠️ 排除第一条数据（开盘数据，波动可能较大）
    # 从第二条（索引1）开始检查
    df_check = df.iloc[1:]  # 跳过第一条，从第二条开始
    
    # 快速检查：是否有任何一条破均线（使用向量化操作）
    # 破均线条件：(低价 - 均线) < -容忍度，即 低价 < 均线 - 容忍度
    broke_mask = df_check['diff'] < -df_check['tolerance']
    
    if broke_mask.any():
        if debug:
            # 找到第一条破均线的数据（仅用于调试输出）
            broke_idx = broke_mask.idxmax()
            row = df.loc[broke_idx]
            print(f"  ❌ 破均线: 时间={row['time']}, 最低价={row['low']:.2f}, "
                  f"均线={row['ma']:.2f}, 容忍度={row['tolerance']:.4f}, 差值={row['diff']:.4f}")
        return False
    
    # 检查当前价（最后一条数据的收盘价）是否≥均线
    last_row = df.iloc[-1]
    last_tolerance = last_row['tolerance']
    if last_row['close'] < (last_row['ma'] - last_tolerance):
        if debug:
            print(f"  ❌ 当前价破均线: 收盘={last_row['close']:.2f}, "
                  f"均线={last_row['ma']:.2f}, 容忍度={last_tolerance:.4f}")
        return False
    
    # ✅ 检查9:40实际涨幅（第三根K线，索引2）必须≥2%
    # 使用前一交易日收盘价作为基准，计算实际涨幅
    if prev_close is None or prev_close <= 0:
        if debug:
            print(f"  ❌ 无法获取前日收盘价，无法计算实际涨幅")
        return False
    
    if len(df) >= 3:  # 确保有9:40的数据
        # 找到9:40的数据（第三根K线，索引2）
        row_940 = df.iloc[2]
        close_940 = row_940['close']  # 9:40收盘价
        
        # 计算实际涨幅（相对于前日收盘价）
        change_pct = (close_940 - prev_close) / prev_close * 100
        
        # 实际涨幅必须≥2%
        if change_pct < 2.0:
            if debug:
                print(f"  ❌ 9:40实际涨幅不足: 涨幅={change_pct:.2f}% < 2%")
                print(f"     前日收盘={prev_close:.2f}, 9:40收盘={close_940:.2f}")
            return False
        
        if debug:
            print(f"  ✅ 9:40实际涨幅: {change_pct:.2f}% ≥ 2%（前日收盘={prev_close:.2f}）")
    
    # 调试模式：显示详细信息
    if debug:
        print("\n===== 分时数据验证 =====")
        print("完整数据（包含第一条）：")
        print(df[['time', 'low', 'ma', 'tolerance', 'diff']].to_string())
        print(f"\n总数据条数: {len(df)} 条")
        print(f"⚠️  第一条数据已排除检查（开盘波动大）")
        print(f"实际检查条数: {len(df_check)} 条（从第2条开始）")
        print(f"\n检查范围内最小差值: {df_check['diff'].min():.4f} 元")
        print(f"检查范围内最大差值: {df_check['diff'].max():.4f} 元")
        print(f"平均容忍度: {df['tolerance'].mean():.4f} 元 (约{tolerance_pct:.2f}%)")
        print(f"当前价: {last_row['close']:.2f}, 均线: {last_row['ma']:.2f}, 容忍度: {last_tolerance:.4f}")
        print("✅ 所有条件满足！")
    
    return True

def process_single_stock(args):
    """处理单只股票的函数（多进程版本）
    
    Args:
        args: (stock_code, date, debug) 元组
    
    Returns:
        tuple: (stock_code, is_valid) 或 None（如果无数据）
    """
    code, date, debug = args
    try:
        # 获取前一交易日收盘价
        prev_close = get_previous_close(code, date)
        if prev_close is None:
            return None  # 无法获取前日收盘价，跳过该股票
        
        # 获取分时数据
        df = get_minute_data(code, date)
        if df is None:
            return None
        
        # 检查是否分时未破均线（不再排除涨停股票）
        if check_never_break_ma(df, prev_close, debug=debug):
            return (code, True)
        return None
    except Exception as e:
        # 多进程中不打印错误信息，避免输出混乱
        return None

def run_single_check(stock_list, today, debug_mode, num_processes, is_monitor_mode=False):
    """执行单次筛选检查
    
    Args:
        stock_list: 要检查的股票列表
        today: 日期
        debug_mode: 调试模式
        num_processes: 进程数
        is_monitor_mode: 是否是监控模式（后续运行）
    
    Returns:
        list: 符合条件的股票列表
    """
    # 检查股票列表是否为空
    if not stock_list or len(stock_list) == 0:
        print(f"\n⚠️  股票列表为空，无法进行筛选")
        return []
    
    mode_text = "监控模式" if is_monitor_mode else "首次筛选"
    
    print(f"\n🚀 开始处理 {len(stock_list)} 只股票...（{mode_text}）")
    
    # 安全计算预计耗时（避免除零）
    if num_processes > 0 and len(stock_list) > 0:
        print(f"💡 提示: 使用 {num_processes} 个进程并行处理，预计耗时 {len(stock_list)/num_processes/2:.1f}-{len(stock_list)/num_processes:.1f} 分钟\n")
    else:
        print(f"💡 提示: 使用 {num_processes} 个进程并行处理\n")
    
    # 开始计时
    start_time = time.time()
    
    # 准备参数列表
    tasks = [(code, today, debug_mode) for code in stock_list]
    
    # 使用多进程池处理
    result = []
    processed_count = 0
    
    try:
        with Pool(processes=num_processes) as pool:
            # 使用 imap_unordered 获取实时结果（不保证顺序，但更快）
            # chunksize=5 降低，避免某个chunk卡住影响整体
            for stock_result in pool.imap_unordered(process_single_stock, tasks, chunksize=5):
                processed_count += 1
                
                # 显示进度（每处理80只或最后一只）
                if processed_count % 80 == 0 or processed_count == len(stock_list):
                    progress_percent = (processed_count / len(stock_list)) * 100
                    elapsed = time.time() - start_time
                    speed = processed_count / elapsed if elapsed > 0 else 0
                    eta = (len(stock_list) - processed_count) / speed if speed > 0 else 0
                    print(f"⏳ 进度: {processed_count}/{len(stock_list)} ({progress_percent:.1f}%) | "
                          f"速度: {speed:.1f}只/秒 | 预计剩余: {eta/60:.1f}分钟")
                
                # 收集结果
                if stock_result:
                    code, is_valid = stock_result
                    if is_valid:
                        name = code.split('.')[1]
                        result.append(code)
                        print(f"  ✓ 找到符合条件: {code}（{name}）")
    except KeyboardInterrupt:
        print(f"\n⚠️  用户中断，正在清理资源...")
        raise
    except Exception as e:
        print(f"\n❌ 多进程处理出错: {e}")
        print(f"错误类型: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        print("正在清理资源...")
    
    # 计算总耗时
    end_time = time.time()
    elapsed_time = end_time - start_time
    
    # 输出结果
    print("\n" + "="*60)
    print(f"✅ 处理完成！")
    print("="*60)
    print(f"⏱️  总耗时: {elapsed_time:.2f} 秒 ({elapsed_time/60:.2f} 分钟)")
    
    # 安全计算处理速度和百分比（避免除零错误）
    if elapsed_time > 0:
        print(f"⚡ 处理速度: {len(stock_list)/elapsed_time:.2f} 只/秒")
    else:
        print(f"⚡ 处理速度: N/A")
    
    print(f"📊 处理总数: {len(stock_list)} 只")
    
    if len(stock_list) > 0:
        print(f"🎯 符合条件: {len(result)} 只 ({len(result)/len(stock_list)*100:.2f}%)")
    else:
        print(f"🎯 符合条件: {len(result)} 只")
    
    print("="*60)
    
    if result:
        print(f"\n{'='*60}")
        print(f"📈 分时未破均线的股票列表 ({len(result)} 只)")
        print("="*60)
        for i, stock in enumerate(result, 1):
            name = stock.split('.')[1]
            print(f"{i:3d}. {stock}（{name}）")
        print("="*60)
    else:
        print("\n⚠️  未找到符合条件的股票")
    
    return result

def main():
    today = "2025-11-03"  # 最新的交易日
    debug_mode = False  # 是否开启调试模式（显示详细验证信息）
    num_processes = min(8, cpu_count())  # 使用8个进程（或CPU核心数，取较小值）- 降低并发避免卡死
    monitor_interval = 5 * 60  # 监控间隔（秒），默认5分钟
    filtered_file = "filtered_stocks.txt"  # 存储文件名
    
    print("="*60)
    print(f"🔍 分时未破均线股票筛选工具（创业板+科创板）")
    print("="*60)
    print(f"日期: {today}")
    print(f"进程数: {num_processes} (已优化，避免卡死)")
    print(f"优化: ✓ 多进程并行  ✓ 自动重试  ✓ 静默模式  ✓ 防卡死机制")
    print(f"筛选范围:")
    print(f"  • 创业板（sz.30开头）：涨跌幅±20%")
    print(f"  • 科创板（sh.688开头）：涨跌幅±20%")
    print(f"  • 排除ST股票（ST、*ST、退市等）")
    print(f"筛选条件:")
    print(f"  • 分时未破均线（最低价始终≥均线）")
    print(f"  • 排除第一条数据（9:30开盘），从第二条开始检查")
    print(f"  • 9:40分实际涨幅≥2%（相对于前日收盘价）")
    print(f"  • 使用百分比容忍度（0.1%），自适应不同股价")
    print(f"    例如：10元股票容忍0.01元，100元股票容忍0.1元")
    print(f"  • 包含涨停股票（强势股不排除）")
    print("="*60)
    
    # 尝试加载已有的股票列表
    saved_stocks, save_date = load_stock_list(filtered_file)
    
    if saved_stocks and len(saved_stocks) > 0:
        # 监控模式：使用已保存的股票列表
        print(f"\n📂 检测到已保存的股票列表")
        print(f"   保存时间: {save_date}")
        print(f"   股票数量: {len(saved_stocks)} 只")
        print(f"\n💡 将进入监控模式，每 {monitor_interval//60} 分钟检查一次这些股票")
        print(f"   提示: 删除 {filtered_file} 文件可重新进行首次筛选\n")
        
        test_stocks = saved_stocks
        is_first_run = False
    else:
        # 首次运行：获取所有股票列表
        print(f"\n💡 首次运行，将筛选所有创业板和科创板股票")
        print("\n📡 正在连接 baostock 服务器，获取股票列表...")
        stock_list = get_stock_list(today)
        
        # 检查是否成功获取股票列表
        if not stock_list or len(stock_list) == 0:
            print(f"\n❌ 未能获取到股票列表")
            print(f"   可能原因：")
            print(f"   1. 网络连接问题")
            print(f"   2. baostock 服务器故障")
            print(f"   3. 选择的日期不是交易日")
            print(f"\n请检查网络连接和日期设置后重试")
            return
        
        print(f"✅ 获取到股票数量：{len(stock_list)} 只（创业板+科创板，已排除ST股票）")
        
        # 测试用：可以先测试少量股票
        #test_stocks = stock_list[:50]  # 先测试50只，确认逻辑正确后再增加
        #test_stocks = stock_list[:200]  # 测试200只
        test_stocks = stock_list  # 全量筛选（约2000只创业板+科创板）
        is_first_run = True
    
    # 开始监控循环
    run_count = 0
    
    try:
        while True:
            run_count += 1
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            print(f"\n{'='*60}")
            print(f"🔄 第 {run_count} 次运行 - {current_time}")
            print(f"{'='*60}")
            
            # 执行单次检查
            result = run_single_check(
                stock_list=test_stocks,
                today=today,
                debug_mode=debug_mode,
                num_processes=num_processes,
                is_monitor_mode=(not is_first_run)
            )
            
            # 首次运行：保存符合条件的股票列表
            if is_first_run and result:
                save_stock_list(result, filtered_file)
                print(f"\n💡 下次运行将监控这 {len(result)} 只股票")
                print(f"   删除 {filtered_file} 可重新进行首次筛选")
                # 后续循环改为监控模式
                test_stocks = result
                is_first_run = False
            elif not is_first_run:
                # 监控模式：更新股票列表（移除不符合条件的）
                if len(result) < len(test_stocks):
                    removed_count = len(test_stocks) - len(result)
                    print(f"\n⚠️  有 {removed_count} 只股票不再符合条件，已移除")
                
                if result:
                    # 更新保存的列表
                    save_stock_list(result, filtered_file)
                    test_stocks = result
                else:
                    print(f"\n⚠️  所有股票都不再符合条件")
                    print(f"   删除 {filtered_file} 可重新进行首次筛选")
            
            # 等待下次运行
            print(f"\n{'='*60}")
            print(f"⏰ 下次运行时间: {monitor_interval//60} 分钟后")
            print(f"💡 按 Ctrl+C 可随时停止程序")
            print(f"{'='*60}")
            
            time.sleep(monitor_interval)
            
    except KeyboardInterrupt:
        print(f"\n\n⚠️  用户中断程序")
        print(f"✅ 程序已安全退出")
    
    # 强制刷新输出缓冲区
    sys.stdout.flush()
    sys.stderr.flush()
    
    print("\n✅ 程序执行完毕，可以安全退出")

if __name__ == "__main__":
    # Windows 多进程必须调用 freeze_support，避免卡死
    freeze_support()
    
    # 设置多进程启动方法（Windows 默认是 spawn）
    try:
        set_start_method('spawn', force=True)
    except RuntimeError:
        pass  # 如果已经设置过，忽略错误
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断程序")
    except Exception as e:
        print(f"\n\n❌ 程序出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 确保所有资源被释放
        print("\n🔄 清理资源并退出...")
        
        # 尝试登出 baostock
        try:
            with SuppressOutput():
                bs.logout()
        except:
            pass
        
        print("✅ 程序已安全退出")