"""
使用Selenium模拟浏览器获取行业板块数据
当push2.eastmoney.com API无法访问时，使用浏览器自动化
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
import time
import json
from datetime import date
from sqlalchemy import create_engine, text
from data_warehouse.config import DATABASE_URL
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_selenium_available():
    """检查Selenium是否可用"""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        return True
    except ImportError:
        logger.error("❌ Selenium未安装，请运行: pip install selenium")
        return False


def fetch_industry_list_with_selenium():
    """
    使用Selenium获取行业板块列表
    访问quote页面，等待数据加载，然后从网络请求中提取数据
    """
    if not check_selenium_available():
        return None
    
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        # 配置Chrome选项
        chrome_options = Options()
        # chrome_options.add_argument('--headless')  # 先不用无头模式，方便调试
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # 启用性能日志，捕获网络请求
        chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
        
        # 尝试启动Chrome（使用webdriver-manager自动管理驱动）
        try:
            try:
                from selenium.webdriver.chrome.service import Service
                from webdriver_manager.chrome import ChromeDriverManager
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=chrome_options)
            except ImportError:
                # 如果没有webdriver-manager，尝试直接使用系统ChromeDriver
                driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            logger.error(f"❌ 无法启动Chrome: {e}")
            logger.error("   请安装: pip install webdriver-manager")
            logger.error("   或手动安装ChromeDriver: brew install chromedriver")
            return None
        
        try:
            logger.info("📥 访问quote页面...")
            url = 'https://quote.eastmoney.com/center/gridlist.html#hs_a_board'
            driver.get(url)
            
            # 等待页面加载
            logger.info("⏳ 等待页面加载...")
            time.sleep(5)
            
            # 尝试切换到行业板块标签
            try:
                # 查找行业板块相关的元素
                wait = WebDriverWait(driver, 10)
                # 可能需要点击行业板块标签
                # 这里需要根据实际页面结构调整
                logger.info("📊 尝试提取数据...")
            except Exception as e:
                logger.warning(f"⚠️ 页面元素定位失败: {e}")
            
            # 方法1: 从网络请求日志中提取API响应
            logger.info("🔍 检查网络请求...")
            logs = driver.get_log('performance')
            
            api_data = None
            for log in logs:
                try:
                    message = json.loads(log['message'])
                    if message['message']['method'] == 'Network.responseReceived':
                        response = message['message']['params']['response']
                        url_response = response.get('url', '')
                        
                        # 查找push2.eastmoney.com的响应
                        if 'push2.eastmoney.com' in url_response and 'clist/get' in url_response:
                            logger.info(f"✅ 找到API响应: {url_response}")
                            
                            # 获取响应内容
                            request_id = message['message']['params']['requestId']
                            try:
                                response_body = driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': request_id})
                                if response_body.get('body'):
                                    data = json.loads(response_body['body'])
                                    if data.get('data') and data['data'].get('diff'):
                                        api_data = data
                                        logger.info(f"✅ 成功提取数据: {len(data['data']['diff'])} 条")
                                        break
                            except Exception as e:
                                logger.debug(f"获取响应体失败: {e}")
                except Exception as e:
                    continue
            
            # 方法2: 如果网络日志方法失败，尝试从页面DOM提取
            if api_data is None:
                logger.info("📄 尝试从页面DOM提取数据...")
                try:
                    # 执行JavaScript获取数据
                    # 这需要根据实际页面的JavaScript结构来调整
                    script = """
                    // 尝试从window对象或全局变量中获取数据
                    if (window.boardData) {
                        return window.boardData;
                    }
                    if (window.__INITIAL_STATE__) {
                        return window.__INITIAL_STATE__;
                    }
                    // 尝试从React/Vue组件的状态中获取
                    return null;
                    """
                    result = driver.execute_script(script)
                    if result:
                        logger.info("✅ 从页面JavaScript获取到数据")
                        api_data = result
                except Exception as e:
                    logger.warning(f"⚠️ 从DOM提取失败: {e}")
            
            # 方法3: 直接调用API（在浏览器环境中）
            if api_data is None:
                logger.info("🌐 尝试在浏览器环境中调用API...")
                try:
                    # 使用execute_async_script处理异步fetch
                    result = driver.execute_async_script("""
                        var callback = arguments[arguments.length - 1];
                        var url = 'https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=500&fs=m:90+t:2&fields=f12,f14';
                        fetch(url, {
                            method: 'GET',
                            headers: {
                                'Referer': 'https://quote.eastmoney.com/',
                                'Origin': 'https://quote.eastmoney.com',
                                'Accept': 'application/json, text/plain, */*',
                                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                            },
                            credentials: 'include'
                        })
                        .then(response => {
                            if (!response.ok) {
                                throw new Error('HTTP ' + response.status);
                            }
                            return response.json();
                        })
                        .then(data => {
                            callback({success: true, data: data});
                        })
                        .catch(error => {
                            console.error('Fetch error:', error);
                            callback({success: false, error: error.toString()});
                        });
                    """)
                    
                    if result and result.get('success') and result.get('data'):
                        api_data = result['data']
                        if api_data.get('data') and api_data['data'].get('diff'):
                            diff_data = api_data['data']['diff']
                            # diff可能是列表或字典
                            if isinstance(diff_data, list):
                                count = len(diff_data)
                            elif isinstance(diff_data, dict):
                                count = len(diff_data)
                            else:
                                count = 0
                            logger.info(f"✅ 在浏览器环境中成功调用API: {count} 条")
                    elif result and not result.get('success'):
                        logger.warning(f"⚠️ API调用失败: {result.get('error', '未知错误')}")
                except Exception as e:
                    logger.warning(f"⚠️ 浏览器环境API调用失败: {e}")
                    import traceback
                    traceback.print_exc()
            
            if api_data and api_data.get('data') and api_data['data'].get('diff'):
                records = []
                diff_data = api_data['data']['diff']
                
                # 检查数据格式：可能是列表或字典
                if isinstance(diff_data, list) and len(diff_data) > 0:
                    # 列表格式：直接遍历
                    for item in diff_data:
                        if isinstance(item, dict):
                            sector_id = item.get('f12', '')
                            name = item.get('f14', '')
                            
                            if sector_id and name:
                                records.append({
                                    'sector_id': sector_id,
                                    'name': name
                                })
                elif isinstance(diff_data, dict):
                    # 字典格式：遍历字典的值
                    for key, item in diff_data.items():
                        if isinstance(item, dict):
                            sector_id = item.get('f12', '')
                            name = item.get('f14', '')
                            
                            if sector_id and name:
                                records.append({
                                    'sector_id': sector_id,
                                    'name': name
                                })
                else:
                    logger.warning(f"⚠️ 数据格式异常: {type(diff_data)}")
                
                if records:
                    df = pd.DataFrame(records)
                    logger.info(f"✅ 成功获取 {len(df)} 个行业板块")
                    logger.info(f"示例: {df.head(3).to_dict('records')}")
                    return df
                else:
                    logger.warning("⚠️ 未能解析出有效数据")
                    # 打印详细调试信息
                    logger.warning(f"api_data类型: {type(api_data)}")
                    if api_data:
                        logger.warning(f"api_data keys: {api_data.keys() if isinstance(api_data, dict) else 'N/A'}")
                        if isinstance(api_data, dict) and 'data' in api_data:
                            logger.warning(f"api_data['data'] keys: {api_data['data'].keys() if isinstance(api_data['data'], dict) else 'N/A'}")
                            if isinstance(api_data['data'], dict) and 'diff' in api_data['data']:
                                diff = api_data['data']['diff']
                                logger.warning(f"diff类型: {type(diff)}, 长度: {len(diff) if isinstance(diff, (list, dict)) else 'N/A'}")
                                if isinstance(diff, list) and len(diff) > 0:
                                    logger.warning(f"diff[0]类型: {type(diff[0])}, 值: {diff[0]}")
                    return None
            else:
                logger.warning("⚠️ 未能提取到数据")
                logger.info("💡 建议：检查页面是否完全加载，或调整等待时间")
                return None
                
        finally:
            driver.quit()
            
    except Exception as e:
        logger.error(f"❌ Selenium获取数据失败: {e}", exc_info=True)
        return None


def fetch_sector_stocks_with_selenium(sector_id: str, sector_name: str):
    """
    使用Selenium获取板块成分股
    """
    if not check_selenium_available():
        return None
    
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
        
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except ImportError:
            driver = webdriver.Chrome(options=chrome_options)
        
        try:
            # 先访问quote页面建立会话
            logger.debug(f"访问quote页面建立会话...")
            driver.get('https://quote.eastmoney.com/center/gridlist.html#hs_a_board')
            time.sleep(2)
            
            # 在浏览器环境中调用API
            result = driver.execute_async_script(f"""
                var callback = arguments[arguments.length - 1];
                var url = 'https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=2000&fs=b:{sector_id}&fields=f12,f14,f13';
                
                // 尝试使用XMLHttpRequest（更兼容）
                var xhr = new XMLHttpRequest();
                xhr.open('GET', url, true);
                xhr.setRequestHeader('Referer', 'https://quote.eastmoney.com/');
                xhr.setRequestHeader('Origin', 'https://quote.eastmoney.com');
                xhr.setRequestHeader('Accept', 'application/json, text/plain, */*');
                
                xhr.onload = function() {{
                    if (xhr.status === 200) {{
                        try {{
                            var data = JSON.parse(xhr.responseText);
                            callback({{success: true, data: data}});
                        }} catch (e) {{
                            callback({{success: false, error: 'JSON parse error: ' + e.toString()}});
                        }}
                    }} else {{
                        callback({{success: false, error: 'HTTP ' + xhr.status}});
                    }}
                }};
                
                xhr.onerror = function() {{
                    callback({{success: false, error: 'Network error'}});
                }};
                
                xhr.send();
            """)
            
            if result and result.get('success') and result.get('data'):
                result = result['data']
            
            if result and result.get('data') and result['data'].get('diff'):
                records = []
                diff_data = result['data']['diff']
                
                # 处理列表或字典格式
                if isinstance(diff_data, list):
                    for item in diff_data:
                        if isinstance(item, dict):
                            code = item.get('f12', '')
                            name = item.get('f14', '')
                            market = item.get('f13', '')
                            
                            if code and name:
                                records.append({
                                    'code': code,
                                    'name': name,
                                    'market': market
                                })
                elif isinstance(diff_data, dict):
                    for key, item in diff_data.items():
                        if isinstance(item, dict):
                            code = item.get('f12', '')
                            name = item.get('f14', '')
                            market = item.get('f13', '')
                            
                            if code and name:
                                records.append({
                                    'code': code,
                                    'name': name,
                                    'market': market
                                })
                
                if records:
                    df = pd.DataFrame(records)
                    logger.info(f"✅ {sector_name} 成功获取 {len(df)} 只成分股")
                    return df
                else:
                    logger.warning(f"⚠️ {sector_name} 未能解析出有效成分股数据")
                    logger.warning(f"  diff类型: {type(diff_data)}, 长度: {len(diff_data) if isinstance(diff_data, (list, dict)) else 'N/A'}")
                    return None
            else:
                if result and not result.get('success'):
                    logger.warning(f"⚠️ {sector_name} API调用失败: {result.get('error', '未知错误')}")
                else:
                    logger.warning(f"⚠️ {sector_name} 无成分股数据")
                    if result:
                        logger.warning(f"  result keys: {result.keys() if isinstance(result, dict) else 'N/A'}")
                return None
                
        finally:
            driver.quit()
            
    except Exception as e:
        logger.warning(f"⚠️ {sector_name} Selenium获取失败: {e}")
        return None


def fill_stock_sector_with_selenium(limit: int = None, delay: float = 2.0, start_from: int = 0):
    """
    使用Selenium补全股票-板块关联数据
    """
    logger.info("="*60)
    logger.info("开始使用Selenium补全股票-板块关联数据")
    logger.info("="*60)
    
    # 获取板块列表
    engine = create_engine(DATABASE_URL, echo=False)
    with engine.connect() as conn:
        sql = """
        SELECT sector_id, name
        FROM dim_sector
        WHERE sector_type = 'industry'
        ORDER BY sector_id
        """
        if limit:
            sql += f" LIMIT {limit}"
        
        result = conn.execute(text(sql))
        sectors = [(row[0], row[1]) for row in result]
    
    total = len(sectors)
    if start_from > 0:
        sectors = sectors[start_from:]
        logger.info(f"从第 {start_from + 1} 个板块开始，剩余 {len(sectors)} 个")
    
    logger.info(f"共需要处理 {total} 个板块，本次处理 {len(sectors)} 个")
    
    success_count = 0
    fail_count = 0
    total_stocks = 0
    today = date.today()
    
    for idx, (sector_id, sector_name) in enumerate(sectors, start=start_from + 1):
        logger.info(f"\n[{idx}/{total}] 处理 {sector_name} ({sector_id})...")
        
        time.sleep(delay)
        
        try:
            df = fetch_sector_stocks_with_selenium(sector_id, sector_name)
            
            if df is None or df.empty:
                logger.warning(f"⚠️ {sector_name} 无成分股数据")
                fail_count += 1
                continue
            
            # 准备关联数据
            stock_sector_rows = []
            for _, row in df.iterrows():
                code = row['code']
                market = row.get('market', 0)
                
                # 转换为ts_code
                if market == 1:
                    ts_code = f"{code}.SH"
                elif market == 0:
                    ts_code = f"{code}.SZ"
                else:
                    if code.startswith('6'):
                        ts_code = f"{code}.SH"
                    else:
                        ts_code = f"{code}.SZ"
                
                stock_sector_rows.append({
                    'ts_code': ts_code,
                    'sector_id': sector_id,
                    'start_date': today,
                    'end_date': None,
                    'is_primary': True,
                })
            
            if not stock_sector_rows:
                logger.warning(f"⚠️ {sector_name} 未解析到有效股票代码")
                fail_count += 1
                continue
            
            # 批量入库
            with engine.connect() as conn:
                temp_table_name = 'temp_stock_sector_import'
                
                conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
                conn.commit()
                
                df_stock_sector = pd.DataFrame(stock_sector_rows)
                df_stock_sector.to_sql(
                    temp_table_name,
                    conn,
                    if_exists='append',
                    index=False,
                    method='multi',
                    chunksize=5000
                )
                conn.commit()
                
                insert_cols = ', '.join(df_stock_sector.columns)
                select_cols_list = []
                for col in df_stock_sector.columns:
                    if col == 'end_date':
                        select_cols_list.append(f"NULLIF({col}, '')::DATE")
                    else:
                        select_cols_list.append(col)
                select_cols = ', '.join(select_cols_list)
                
                sql = f"""
                INSERT INTO fact_stock_sector 
                ({insert_cols})
                SELECT {select_cols}
                FROM {temp_table_name}
                ON CONFLICT (ts_code, sector_id, start_date) 
                DO NOTHING
                """
                
                conn.execute(text(sql))
                conn.commit()
                
                conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
                conn.commit()
            
            success_count += 1
            total_stocks += len(stock_sector_rows)
            logger.info(f"✅ {sector_name} 成功导入 {len(stock_sector_rows)} 条关联数据")
            
        except Exception as e:
            logger.error(f"❌ {sector_name} 处理失败: {e}", exc_info=True)
            fail_count += 1
        
        if idx % 10 == 0:
            logger.info(f"\n进度: {idx}/{total} ({idx*100//total}%) | 成功: {success_count} | 失败: {fail_count} | 总股票数: {total_stocks}")
    
    logger.info("\n" + "="*60)
    logger.info("股票-板块关联数据补全完成")
    logger.info(f"总计: {total} 个板块 | 成功: {success_count} | 失败: {fail_count} | 总股票数: {total_stocks}")
    logger.info("="*60)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='使用Selenium补全行业板块数据')
    parser.add_argument('--fetch-industry', action='store_true', help='获取行业板块列表')
    parser.add_argument('--fill-stock-sector', action='store_true', help='补全股票-板块关联')
    parser.add_argument('--limit', type=int, default=None, help='限制板块数量（用于测试）')
    parser.add_argument('--delay', type=float, default=2.0, help='每次请求延迟（秒）')
    parser.add_argument('--start-from', type=int, default=0, help='从第几个板块开始')
    
    args = parser.parse_args()
    
    if args.fetch_industry:
        df = fetch_industry_list_with_selenium()
        if df is not None:
            print(f"\n✅ 成功获取 {len(df)} 个行业板块")
            print(df.head())
    
    if args.fill_stock_sector:
        fill_stock_sector_with_selenium(limit=args.limit, delay=args.delay, start_from=args.start_from)
