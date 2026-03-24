"""
东方财富股吧人气榜爬虫

爬取页面: https://guba.eastmoney.com/rank/
数据量: 前100条排名数据
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import time
import logging
import requests
from datetime import datetime
from typing import List, Dict, Optional

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

from backend.scripts.crawler.browser_driver import create_chrome_driver
from backend.scripts.crawler.guba_parser import GubaHtmlParser
from backend.scripts.crawler.guba_repository import save_popularity_ranks

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://guba.eastmoney.com/',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}


class GubaPopularityCrawler:
    """股吧人气榜爬虫"""

    def __init__(self, skip_api: bool = True):
        self.url = "https://guba.eastmoney.com/rank/"
        self.skip_api = skip_api
        self.headers = DEFAULT_HEADERS
        self.timeout = 30
        self._parser = GubaHtmlParser(save_html_path=Path("data_warehouse/guba_popularity/guba_rank_page.html"))

    def try_fetch_api(self) -> Optional[List[Dict]]:
        """尝试从 API 获取数据（通常不可用）"""
        for api_url in [
            "https://guba.eastmoney.com/api/rank/list",
            "https://push2.eastmoney.com/api/qt/clist/get",
            "https://guba.eastmoney.com/rank/api/list",
        ]:
            try:
                r = requests.get(api_url, headers=self.headers, params={'limit': 100, 'page': 1}, timeout=self.timeout)
                if r.status_code == 200:
                    data = r.json()
                    parsed = self._parse_api_response(data)
                    if parsed:
                        logger.info(f"✅ API 成功: {api_url}")
                        return parsed
            except Exception as e:
                logger.debug(f"API {api_url} 失败: {e}")
        return None

    def _parse_api_response(self, data: Dict) -> List[Dict]:
        """解析 API 响应（TODO: 根据实际格式实现）"""
        return []

    def crawl(self, limit: int = 100) -> List[Dict]:
        """爬取人气榜数据"""
        if not self.skip_api:
            api_data = self.try_fetch_api()
            if api_data:
                return api_data[:limit] if limit > 0 else api_data

        if not SELENIUM_AVAILABLE:
            logger.error("请安装: pip install selenium")
            return []

        max_pages = (limit // 20) + 1 if limit > 0 else 5
        results = self._fetch_with_selenium(max_pages)
        if not results:
            return []

        results.sort(key=lambda x: (x.get('rank_position', 999999), x.get('ts_code', '')))
        return results[:limit] if limit > 0 else results

    def _fetch_with_selenium(self, max_pages: int) -> List[Dict]:
        """使用 Selenium 获取多页数据"""
        driver = create_chrome_driver(self.headers["User-Agent"])
        if not driver:
            return []

        try:
            driver.set_page_load_timeout(30)
            driver.implicitly_wait(5)
            driver.get(self.url)
        except TimeoutException:
            logger.warning("页面加载超时，继续尝试...")
        except Exception as e:
            logger.error(f"页面加载失败: {e}")
            return []

        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "rankCont")))
            WebDriverWait(driver, 20).until(lambda d: _data_loaded(d))
            time.sleep(3)
            _try_scroll_load_more(driver)
        except TimeoutException:
            logger.warning("等待数据超时")

        try:
            all_results = []
            rank_offset = 0
            for page in range(1, max_pages + 1):
                time.sleep(2)
                html = driver.page_source
                page_results = self._parser.parse(html, skip_save=(page < max_pages), rank_offset=rank_offset)
                all_results.extend(page_results)
                rank_offset += len(page_results)
                logger.info(f"第 {page} 页: {len(page_results)} 条, 累计 {len(all_results)}")

                if page < max_pages and not _click_next_page(driver, page):
                    break

            return all_results
        finally:
            driver.quit()

    def save_to_file(self, data: List[Dict], filename: str = None):
        """保存到 JSON 文件"""
        import json
        path = Path("data_warehouse/guba_popularity") / (filename or f"guba_rank_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        logger.info(f"已保存: {path}")

    def save_to_database(self, data: List[Dict]) -> bool:
        """保存到数据库"""
        try:
            return save_popularity_ranks(data)
        except Exception as e:
            logger.error(f"保存到数据库失败: {e}", exc_info=True)
            return False


def _data_loaded(driver) -> bool:
    """检查数据是否加载完成"""
    try:
        cont = driver.find_element(By.ID, "rankCont")
        if cont.text.strip():
            return True
        if driver.find_elements(By.TAG_NAME, "table"):
            return True
        if driver.find_elements(By.CSS_SELECTOR, ".rank-item, .rank-row, tr[data-code], tbody tr"):
            return True
    except Exception:
        pass
    return False


def _try_scroll_load_more(driver):
    """尝试滚动触发懒加载"""
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        for btn in driver.find_elements(By.CSS_SELECTOR, ".load-more, .more-btn, [class*='more'], [class*='load']"):
            try:
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(2)
            except Exception:
                pass
        time.sleep(2)
    except Exception as e:
        logger.debug(f"滚动加载: {e}")


def _click_next_page(driver, current_page: int) -> bool:
    """点击下一页"""
    next_num = current_page + 1
    # CSS 选择器
    elems = driver.find_elements(By.CSS_SELECTOR, f".pager a.go_page[data-page='{next_num}']")
    if not elems:
        for link in driver.find_elements(By.CSS_SELECTOR, ".pager a.go_page"):
            if "下一页" in (link.text or "") or link.get_attribute("data-page") == str(next_num):
                elems = [link]
                break
    if not elems:
        elems = driver.find_elements(By.XPATH, "//a[@class='go_page' and contains(text(), '下一页')]")
    for e in elems:
        try:
            driver.execute_script("arguments[0].click();", e)
            time.sleep(3)
            return True
        except Exception:
            pass
    logger.warning("未找到下一页按钮")
    return False


def main():
    import argparse
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    parser = argparse.ArgumentParser(description='股吧人气榜爬虫')
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--no-db', action='store_true', help='不保存到数据库')
    parser.add_argument('--try-api', action='store_true')
    args = parser.parse_args()

    crawler = GubaPopularityCrawler(skip_api=not args.try_api)
    logger.info(f"开始爬取，限制 {args.limit} 条")
    data = crawler.crawl(limit=args.limit)

    if data:
        crawler.save_to_file(data)
        if not args.no_db:
            ok = crawler.save_to_database(data)
            logger.info("✅ 数据库保存成功" if ok else "⚠️ 数据库保存失败")
    else:
        logger.warning("未爬取到数据")


if __name__ == '__main__':
    main()
