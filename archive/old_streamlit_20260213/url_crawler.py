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
        # 尝试读取Excel文件
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
            # 如果upload_time为空，使用当前日期
            now = datetime.now()
            return now.year, now.month, now.day
        
        # 尝试解析日期
        if isinstance(upload_time, str):
            # 如果是字符串，尝试解析
            date_patterns = [
                r'(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})',  # 2024/1/1 或 2024-1-1
                r'(\d{4})(\d{2})(\d{2})',  # 20240101
                r'(\d{4})年(\d{1,2})月(\d{1,2})日',  # 2024年1月1日
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, upload_time)
                if match:
                    year, month, day = match.groups()
                    try:
                        return int(year), int(month), int(day)
                    except ValueError:
                        continue
        
        # 如果是datetime对象
        if hasattr(upload_time, 'year'):
            return upload_time.year, upload_time.month, upload_time.day
        
        # 尝试转换为datetime
        parsed_date = pd.to_datetime(upload_time)
        return parsed_date.year, parsed_date.month, parsed_date.day
        
    except Exception as e:
        print(f"解析日期失败 {upload_time}: {e}")
        # 使用当前日期作为备选
        now = datetime.now()
        return now.year, now.month, now.day

def create_directory_structure(year, month):
    """创建年份/月份目录结构"""
    base_dir = Path("crawled_content")
    year_dir = base_dir / str(year)
    month_dir = year_dir / f"{month:02d}"
    
    # 使用parents=True确保创建所有父目录
    month_dir.mkdir(parents=True, exist_ok=True)
    
    return month_dir

def sanitize_filename(filename):
    """清理文件名，移除非法字符"""
    # 移除或替换非法字符
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # 限制长度
    if len(filename) > 100:
        filename = filename[:100]
    return filename

def remove_images_from_html(html_content):
    """从HTML内容中移除图片标签"""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 移除所有img标签
        for img in soup.find_all('img'):
            img.decompose()
        
        # 移除可能包含封面图的div或其他容器
        # 常见的封面图容器类名
        cover_selectors = [
            '.cover-image', '.cover-img', '.header-image', '.header-img',
            '.featured-image', '.featured-img', '.main-image', '.main-img',
            '.article-image', '.article-img', '.post-image', '.post-img',
            '.banner-image', '.banner-img', '.hero-image', '.hero-img',
            '[class*="cover"]', '[class*="header"]', '[class*="featured"]',
            '[class*="banner"]', '[class*="hero"]'
        ]
        
        for selector in cover_selectors:
            elements = soup.select(selector)
            for element in elements:
                element.decompose()
        
        # 移除空的图片容器
        empty_containers = soup.find_all(['div', 'span', 'p'], string=lambda text: text and text.strip() == '')
        for container in empty_containers:
            if not container.find_all():  # 如果容器内没有其他元素
                container.decompose()
        
        return str(soup)
        
    except Exception as e:
        print(f"处理HTML内容时出错: {e}")
        # 如果BeautifulSoup处理失败，返回原始内容
        return html_content

def crawl_url(url, title, save_dir, index):
    """爬取单个URL的内容并保存"""
    try:
        # 添加请求头，模拟浏览器
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        print(f"正在爬取 [{index}]: {title}")
        print(f"URL: {url}")
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # 检测编码
        if response.encoding == 'ISO-8859-1':
            response.encoding = response.apparent_encoding
        
        # 移除图片内容
        cleaned_html = remove_images_from_html(response.text)
        
        # 生成文件名 - 使用标题作为文件名
        if title and not pd.isna(title):
            # 使用文章标题作为文件名
            filename = f"{index:04d}_{sanitize_filename(str(title))}.html"
        else:
            # 如果没有标题，使用URL信息
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
    
    # 读取Excel数据
    df = read_excel_data(excel_file)
    if df is None:
        return
    
    # 检查必需的列是否存在
    required_columns = ['content_title', 'content_url', 'upload_time']
    missing_columns = [col for col in required_columns if col not in df.columns]
    
    if missing_columns:
        print(f"缺少必需的列: {missing_columns}")
        print(f"可用的列名: {list(df.columns)}")
        return
    
    print(f"找到所有必需的列: {required_columns}")
    
    # 获取非空的数据行
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
        
        # 从upload_time提取日期
        year, month, day = extract_date_from_upload_time(upload_time)
        print(f"提取的日期: {year}年{month}月{day}日")
        
        # 创建目录
        save_dir = create_directory_structure(year, month)
        
        # 爬取并保存
        if crawl_url(content_url, content_title, save_dir, index + 1):
            success_count += 1
        else:
            fail_count += 1
        
        # 添加延迟，避免请求过于频繁
        time.sleep(1)
    
    print(f"\n处理完成:")
    print(f"成功: {success_count}")
    print(f"失败: {fail_count}")
    print(f"总计: {success_count + fail_count}")

if __name__ == "__main__":
    main()
