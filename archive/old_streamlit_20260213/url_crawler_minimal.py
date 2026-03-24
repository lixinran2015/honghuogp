# -*- coding: utf-8 -*-
import pandas as pd
import requests
import os
from datetime import datetime
from urllib.parse import urlparse
import time
import re
from pathlib import Path
from bs4 import BeautifulSoup

def read_excel_data(file_path):
    """读取Excel文件中的数据"""
    try:
        df = pd.read_excel(file_path)
        print(f"成功读取Excel文件，共{len(df)}行数据")
        print(f"列名: {list(df.columns)}")
        return df
    except Exception as e:
        print(f"读取Excel文件失败: {e}")
        return None

def extract_date_from_upload_time(upload_time):
    """从upload_time字段提取日期信息"""
    try:
        if pd.isna(upload_time):
            now = datetime.now()
            return now.year, now.month, now.day
        
        if isinstance(upload_time, str):
            date_patterns = [
                r'(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})',
                r'(\d{4})(\d{2})(\d{2})',
                r'(\d{4})年(\d{1,2})月(\d{1,2})日',
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, upload_time)
                if match:
                    year, month, day = match.groups()
                    try:
                        return int(year), int(month), int(day)
                    except ValueError:
                        continue
        
        if hasattr(upload_time, 'year'):
            return upload_time.year, upload_time.month, upload_time.day
        
        parsed_date = pd.to_datetime(upload_time)
        return parsed_date.year, parsed_date.month, parsed_date.day
        
    except Exception as e:
        print(f"解析日期失败 {upload_time}: {e}")
        now = datetime.now()
        return now.year, now.month, now.day

def create_directory_structure(year, month):
    """创建年份/月份目录结构"""
    base_dir = Path("crawled_content_minimal")
    year_dir = base_dir / str(year)
    month_dir = year_dir / f"{month:02d}"
    month_dir.mkdir(parents=True, exist_ok=True)
    return month_dir

def sanitize_filename(filename):
    """清理文件名，移除非法字符"""
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    if len(filename) > 100:
        filename = filename[:100]
    return filename

def extract_article_content(html_content, original_title, original_time):
    """提取文章内容，只保留标题、正文和发布时间"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 移除所有script、style、link、img、iframe等标签
        for tag in soup.find_all(['script', 'style', 'link', 'img', 'iframe', 'noscript']):
            tag.decompose()
        
        # 尝试找到文章标题
        title = original_title
        if not title or pd.isna(title):
            # 尝试从HTML中提取标题
            title_selectors = [
                'h1', '.title', '.headline', '.article-title', '.post-title',
                '[class*="title"]', '[class*="headline"]'
            ]
            for selector in title_selectors:
                elements = soup.select(selector)
                if elements:
                    title = elements[0].get_text(strip=True)
                    break
        
        # 尝试找到发布时间
        publish_time = original_time
        if not publish_time or pd.isna(publish_time):
            # 尝试从HTML中提取时间
            time_selectors = [
                '.time', '.date', '.publish-time', '.post-time', '.article-time',
                '[class*="time"]', '[class*="date"]', 'time'
            ]
            for selector in time_selectors:
                elements = soup.select(selector)
                if elements:
                    publish_time = elements[0].get_text(strip=True)
                    break
        
        # 尝试找到文章正文 - 更全面的选择器
        content_selectors = [
            # 微信公众平台
            '.rich_media_content', '.rich_media_area_primary', '.rich_media_area_primary_inner',
            # 通用文章容器
            '.article-content', '.article-body', '.post-content', '.post-body',
            '.content', '.main-content', '.entry-content', '.story-content',
            'article', '.article', '.post', '.entry', '.story',
            # 更宽泛的选择器
            '[class*="content"]', '[class*="article"]', '[class*="post"]',
            '[class*="text"]', '[class*="body"]',
            # 微信特定
            '.rich_media', '.rich_media_inner', '.rich_media_area_extra',
            # 其他可能的容器
            '.main', '.main-body', '.text-content', '.article-text'
        ]
        
        article_content = None
        for selector in content_selectors:
            elements = soup.select(selector)
            if elements:
                # 检查内容长度，选择最长的
                for element in elements:
                    text_length = len(element.get_text(strip=True))
                    if text_length > 100:  # 确保有足够的内容
                        article_content = element
                        print(f"找到内容容器: {selector}, 长度: {text_length}")
                        break
                if article_content:
                    break
        
        # 如果没有找到特定的文章容器，尝试body
        if not article_content:
            body = soup.find('body')
            if body:
                # 移除导航、页脚等无关元素
                for unwanted in body.find_all(['nav', 'header', 'footer', 'aside', 'menu', 'script', 'style']):
                    unwanted.decompose()
                article_content = body
                print("使用body作为内容容器")
        
        # 如果还是没有找到，使用整个HTML
        if not article_content:
            article_content = soup
            print("使用整个HTML作为内容容器")
        
        # 获取纯文本内容
        content_text = article_content.get_text(separator='\n', strip=True)
        
        # 清理文本内容
        lines = content_text.split('\n')
        cleaned_lines = []
        for line in lines:
            line = line.strip()
            # 过滤掉太短的行和常见的无关文本
            if (line and 
                len(line) > 5 and 
                not line.startswith('微信') and
                not line.startswith('关注') and
                not line.startswith('点击') and
                not line.startswith('阅读') and
                not line.startswith('分享') and
                not line.startswith('点赞') and
                not line.startswith('在看') and
                not 'copyright' in line.lower() and
                not '版权所有' in line and
                not '微信公众平台' in line):
                cleaned_lines.append(line)
        
        content_text = '\n\n'.join(cleaned_lines)
        
        print(f"提取的内容长度: {len(content_text)}")
        if len(content_text) < 50:
            print("警告: 提取的内容太短，可能没有正确识别文章内容")
        
        # 创建极简的HTML
        minimal_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title or '文章内容'}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
            line-height: 1.8;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            color: #333;
            background-color: #fafafa;
        }}
        .container {{
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            font-size: 28px;
            margin-bottom: 10px;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        .meta {{
            color: #7f8c8d;
            font-size: 14px;
            margin-bottom: 30px;
            padding: 10px;
            background: #ecf0f1;
            border-radius: 4px;
        }}
        .content {{
            font-size: 16px;
            text-align: justify;
            white-space: pre-line;
        }}
        .content p {{
            margin-bottom: 1.2em;
            text-indent: 2em;
        }}
        .content h2, .content h3, .content h4 {{
            color: #34495e;
            margin-top: 1.5em;
            margin-bottom: 0.8em;
        }}
        .content blockquote {{
            border-left: 4px solid #3498db;
            margin: 1em 0;
            padding: 0.5em 1em;
            background: #f8f9fa;
            color: #555;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{title or '文章标题'}</h1>
        <div class="meta">
            发布时间：{publish_time or '未知时间'}
        </div>
        <div class="content">
            {content_text if content_text else '未能提取到文章内容'}
        </div>
    </div>
</body>
</html>"""
        
        return minimal_html
        
    except Exception as e:
        print(f"处理HTML内容时出错: {e}")
        # 返回最基本的HTML结构
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <title>{original_title or '文章内容'}</title>
</head>
<body>
    <h1>{original_title or '文章标题'}</h1>
    <p>发布时间：{original_time or '未知时间'}</p>
    <div>内容提取失败: {str(e)}</div>
</body>
</html>"""

def crawl_url(url, title, upload_time, save_dir, index):
    """爬取单个URL的内容并保存"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        print(f"正在爬取 [{index}]: {title}")
        print(f"URL: {url}")
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        if response.encoding == 'ISO-8859-1':
            response.encoding = response.apparent_encoding
        
        # 提取和清理文章内容
        cleaned_html = extract_article_content(response.text, title, upload_time)
        
        # 生成文件名
        if title and not pd.isna(title):
            filename = f"{index:04d}_{sanitize_filename(str(title))}.html"
        else:
            parsed_url = urlparse(url)
            domain = parsed_url.netloc.replace('.', '_')
            path = parsed_url.path.replace('/', '_').replace('.', '_')
            if not path:
                path = 'index'
            filename = f"{index:04d}_{domain}{path}.html"
        
        filename = sanitize_filename(filename)
        
        # 保存文件
        file_path = save_dir / filename
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(cleaned_html)
        
        print(f"成功保存: {file_path}")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"爬取失败 {url}: {e}")
        return False
    except Exception as e:
        print(f"保存失败 {url}: {e}")
        return False

def main():
    """主函数"""
    excel_file = "data2.xlsx"
    
    df = read_excel_data(excel_file)
    if df is None:
        return
    
    required_columns = ['content_title', 'content_url', 'upload_time']
    missing_columns = [col for col in required_columns if col not in df.columns]
    
    if missing_columns:
        print(f"缺少必需的列: {missing_columns}")
        print(f"可用的列名: {list(df.columns)}")
        return
    
    print(f"找到所有必需的列: {required_columns}")
    
    valid_data = df[['content_title', 'content_url', 'upload_time']].dropna(subset=['content_url'])
    print(f"找到 {len(valid_data)} 个有效数据行")
    
    success_count = 0
    fail_count = 0
    
    for index, row in valid_data.iterrows():
        content_title = row['content_title']
        content_url = row['content_url']
        upload_time = row['upload_time']
        
        if pd.isna(content_url) or not isinstance(content_url, str):
            continue
        
        year, month, day = extract_date_from_upload_time(upload_time)
        print(f"提取的日期: {year}年{month}月{day}日")
        
        save_dir = create_directory_structure(year, month)
        
        if crawl_url(content_url, content_title, upload_time, save_dir, index + 1):
            success_count += 1
        else:
            fail_count += 1
        
        time.sleep(1)
    
    print(f"\n处理完成:")
    print(f"成功: {success_count}")
    print(f"失败: {fail_count}")
    print(f"总计: {success_count + fail_count}")

if __name__ == "__main__":
    main() 