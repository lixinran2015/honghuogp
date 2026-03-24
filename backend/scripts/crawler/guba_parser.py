"""
股吧人气榜 HTML 解析器
"""
import re
import logging
from pathlib import Path
from typing import List, Dict, Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class GubaHtmlParser:
    """解析东方财富股吧人气榜 HTML"""

    def __init__(self, save_html_path: Optional[Path] = None):
        self.save_html_path = save_html_path

    def parse(self, html_content: str, skip_save: bool = False, rank_offset: int = 0) -> List[Dict]:
        """解析 HTML，返回排名数据列表"""
        if not skip_save and self.save_html_path:
            self._save_html(html_content)

        soup = BeautifulSoup(html_content, 'html.parser')
        table = self._find_table(soup)
        if not table:
            return []

        rows = self._get_data_rows(table)
        if not rows:
            return []

        results = []
        for idx, row in enumerate(rows):
            data = self._parse_row(row, idx, rank_offset)
            if data:
                results.append(data)
        return results

    def _save_html(self, content: str) -> None:
        """保存 HTML 用于调试"""
        if not self.save_html_path:
            return
        self.save_html_path.parent.mkdir(parents=True, exist_ok=True)
        self.save_html_path.write_text(content, encoding='utf-8')
        logger.info(f"HTML 已保存: {self.save_html_path}")

    def _find_table(self, soup: BeautifulSoup):
        """查找数据表格容器"""
        table = soup.find('table')
        if not table:
            table = soup.find('div', class_=lambda x: x and 'rank' in (x or '').lower())
        if not table:
            logger.warning("未找到表格")
            scripts = soup.find_all('script')
            for s in scripts:
                if s.string and 'rank' in (s.string or '').lower():
                    logger.info("发现 script 中可能的 JSON 数据")
        return table

    def _get_data_rows(self, table) -> List:
        """获取数据行，跳过表头"""
        tbody = table.find('tbody', class_='stock_tbody') if hasattr(table, 'name') and table.name == 'table' else None
        rows = tbody.find_all('tr') if tbody else table.find_all('tr')
        if rows and len(rows) > 1:
            first = rows[0]
            if 'tabhead' in first.get('class', []) or first.find('th'):
                rows = rows[1:]
        return rows

    def _parse_row(self, row, idx: int, rank_offset: int) -> Optional[Dict]:
        """解析单行数据"""
        if 'tabhead' in row.get('class', []):
            return None

        cells = row.find_all('td')
        if len(cells) < 9:
            return None

        rank_position = self._extract_rank(cells[0], idx, rank_offset, cells)
        if rank_position is None:
            return None

        rank_change = self._extract_rank_change(cells[1])
        ts_code = self._format_ts_code(self._text_from_cell(cells[3], 'stock_code'))
        stock_name = self._text_from_cell(cells[4], 'stock_name', use_title=True) or self._cell_text(cells[4])

        if not ts_code and not stock_name:
            return None

        latest_price = self._safe_float(self._text_from_div(cells[6], 'price')) if len(cells) > 6 else None
        change_amount = self._safe_float(self._text_from_div(cells[7], 'zde')) if len(cells) > 7 else None
        change_pct_raw = self._text_from_div(cells[8], 'zdf') if len(cells) > 8 else ''
        change_pct = self._safe_float(change_pct_raw.rstrip('%')) if change_pct_raw else None

        new_fans = loyal_fans = None
        if len(cells) > 9:
            fans_td = cells[9]
            left = fans_td.find('span', class_='left_percent')
            right = fans_td.find('span', class_='right_percent')
            new_fans = self._safe_float(left.get_text(strip=True).rstrip('%')) if left else None
            loyal_fans = self._safe_float(right.get_text(strip=True).rstrip('%')) if right else None

        return {
            'rank_position': rank_position,
            'rank_change': rank_change,
            'ts_code': ts_code or stock_name or 'UNKNOWN',
            'stock_name': stock_name or ts_code or 'UNKNOWN',
            'latest_price': latest_price,
            'change_amount': change_amount,
            'change_pct': change_pct,
            'new_fans': new_fans,
            'loyal_fans': loyal_fans,
        }

    def _extract_rank(self, rank_td, idx: int, rank_offset: int, cells: list) -> Optional[int]:
        """提取排名"""
        if rank_td:
            div = rank_td.find('div')
            text = div.get_text(strip=True) if div else rank_td.get_text(strip=True)
            m = re.search(r'(\d+)', text) if text else None
            if m:
                return int(m.group(1))
            for attr in ('data-rank', 'data-position', 'rank'):
                val = rank_td.get(attr)
                if val and str(val).isdigit():
                    return int(val)

        has_data = (len(cells) > 3 and self._cell_text(cells[3])) or (len(cells) > 4 and self._cell_text(cells[4]))
        if has_data:
            return idx + 1 + rank_offset
        return None

    def _extract_rank_change(self, change_td) -> int:
        """解析排名变动"""
        if not change_td:
            return 0
        div = change_td.find('div')
        if not div:
            return self._parse_rank_change(change_td.get_text(strip=True))

        icon_b = div.find('b', class_='changeicon')
        text = div.get_text(strip=True)
        if icon_b:
            classes = icon_b.get('class', [])
            is_up = 'icon_rankup' in classes
            is_down = 'icon_rankdown' in classes
            m = re.search(r'(-?\d+)', text)
            if m:
                n = int(m.group(1))
                return n if is_up else (-n if is_down else n)
        return self._parse_rank_change(text)

    def _parse_rank_change(self, text: str) -> int:
        if not text or text == '-':
            return 0
        if '↑' in text:
            n = text.replace('↑', '').strip()
            return int(n) if n.isdigit() else 0
        if '↓' in text:
            n = text.replace('↓', '').strip()
            return -int(n) if n.isdigit() else 0
        return 0

    def _text_from_cell(self, cell, class_part: str, use_title: bool = False) -> str:
        """从 cell 中按 class 查找链接文本"""
        if not cell:
            return ''
        link = cell.find('a', class_=lambda x: x and class_part in (x or ''))
        if link:
            return (link.get('title') if use_title else None) or link.get_text(strip=True) or ''
        return cell.get_text(strip=True) or ''

    def _text_from_div(self, cell, class_part: str) -> Optional[str]:
        """从 cell 的 div 中提取文本"""
        if not cell:
            return None
        div = cell.find('div', class_=lambda x: x and class_part in (x or ''))
        return div.get_text(strip=True) if div else None

    def _cell_text(self, cell) -> str:
        return cell.get_text(strip=True) if cell else ''

    def _format_ts_code(self, code: str) -> str:
        if not code:
            return ''
        code = str(code).strip()
        if '.' in code:
            return code
        if len(code) == 6:
            if code.startswith(('00', '30')):
                return f"{code}.SZ"
            if code.startswith(('60', '68')):
                return f"{code}.SH"
        return code

    def _safe_float(self, value) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        try:
            cleaned = str(value).replace(',', '').replace('，', '').replace('%', '')
            return float(cleaned)
        except (ValueError, AttributeError):
            return None
