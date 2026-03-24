# 股吧人气榜爬虫 - 下一步操作指南

## 🔍 当前状态

✅ **已完成**：
1. 爬虫框架代码已创建
2. 已识别页面是JavaScript动态加载
3. 已添加API尝试和Selenium支持
4. HTML内容已保存到 `data_warehouse/guba_popularity/guba_rank_page.html`

❌ **待完成**：
1. 页面结构分析（需要打开保存的HTML或使用浏览器访问）
2. 完善解析逻辑（根据实际HTML结构）
3. 测试Selenium获取完整数据

## 📋 方案选择

根据页面分析，有两种方案：

### 方案A: 使用Selenium（推荐，最可靠）

**优点**：
- 可以获取JavaScript渲染后的完整数据
- 不受页面结构变化影响
- 可以模拟真实浏览器行为

**步骤**：
1. 安装Selenium：`pip install selenium webdriver-manager`
2. 使用Selenium获取完整页面
3. 等待数据加载完成后解析

**代码**：
```python
# 在命令行运行
python backend/scripts/crawler/guba_popularity_crawler.py --use-selenium
```

### 方案B: 查找API接口（最快，但可能不稳定）

**优点**：
- 速度快
- 数据格式规范
- 资源消耗小

**步骤**：
1. 打开浏览器开发者工具（F12）
2. 访问 https://guba.eastmoney.com/rank/
3. 查看 Network 标签，筛选 XHR/Fetch
4. 查找数据请求（通常是JSON格式）
5. 找到API接口后，直接调用

## 🚀 立即操作步骤

### 步骤1: 安装Selenium（如未安装）

```bash
pip install selenium webdriver-manager
```

### 步骤2: 使用Selenium测试

```bash
# 修改代码，强制使用Selenium
python backend/scripts/crawler/guba_popularity_crawler.py
```

或者修改 `main()` 函数：
```python
crawler = GubaPopularityCrawler(use_selenium=True)  # 强制使用Selenium
```

### 步骤3: 分析页面结构

1. **使用浏览器访问页面**
   - 打开 https://guba.eastmoney.com/rank/
   - 按 F12 打开开发者工具
   - 等待页面完全加载

2. **查看Network请求**
   - 切换到 Network 标签
   - 筛选 XHR 或 Fetch
   - 查找数据请求（通常是包含 `rank` 或 `list` 的请求）

3. **分析HTML结构**
   - 切换到 Elements 标签
   - 查找排名数据的HTML元素
   - 记录关键的 class、id 等选择器

### 步骤4: 完善解析逻辑

根据实际页面结构，修改 `parse_html` 方法：

```python
def parse_html(self, html_content: str) -> List[Dict]:
    soup = BeautifulSoup(html_content, 'html.parser')
    results = []
    
    # 根据实际页面结构调整选择器
    # 示例1: 如果数据在表格中
    table = soup.find('table', {'class': '实际的class名称'})
    rows = table.find('tbody').find_all('tr')
    
    # 示例2: 如果数据在div列表中
    # items = soup.find_all('div', {'class': 'rank-item'})
    
    # 解析数据...
    return results
```

## 🔧 调试技巧

### 1. 保存完整HTML用于分析

代码已经自动保存HTML到 `data_warehouse/guba_popularity/guba_rank_page.html`

### 2. 打印关键元素

在 `parse_html` 方法中添加调试代码：
```python
# 打印rankCont容器的内容
rank_cont = soup.find('div', id='rankCont')
if rank_cont:
    print("rankCont内容:", rank_cont.text[:500])
    print("rankCont HTML:", str(rank_cont)[:1000])
```

### 3. 检查JavaScript加载的数据

使用Selenium时，可以直接执行JavaScript获取数据：
```python
# 在Selenium中执行JavaScript
data = driver.execute_script("return window.rankData;")  # 假设数据在window.rankData中
```

## 📝 需要的信息

为了完善解析逻辑，需要以下信息：

1. **页面结构**：
   - 排名数据在什么HTML元素中？（table/div/ul等）
   - 每个字段对应的选择器是什么？

2. **API接口**（如果存在）：
   - API地址是什么？
   - 请求参数是什么？
   - 响应格式是什么？

3. **数据格式**：
   - 股票代码格式是什么？（如：000001.SZ 还是 000001）
   - 排名变动如何表示？（↑5、↓3、-）

## 🎯 下一步

1. **立即执行**：使用Selenium获取完整页面
2. **分析页面**：查看实际HTML结构
3. **完善解析**：根据实际结构调整代码
4. **测试验证**：确保能正确提取所有字段

