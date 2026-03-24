# Selenium方案 - 行业板块数据获取

## 问题背景

`push2.eastmoney.com` API 长期不稳定，无法直接通过 HTTP 请求获取行业板块数据。

## 解决方案

使用 **Selenium** 模拟真实浏览器，在浏览器环境中调用 API，绕过服务器端的访问限制。

## 实现原理

1. **启动 Chrome 浏览器**（无头模式）
2. **访问 quote.eastmoney.com 页面**，建立浏览器会话
3. **在浏览器环境中执行 JavaScript**，调用 `push2.eastmoney.com` API
4. **提取返回的数据**，解析并写入数据库

## 优势

- ✅ **绕过 API 访问限制**：模拟真实浏览器环境
- ✅ **可以执行 JavaScript**：利用浏览器的完整功能
- ✅ **数据格式正确**：返回的数据与直接调用 API 一致

## 使用方法

### 1. 安装依赖

```bash
pip install selenium webdriver-manager
```

### 2. 获取行业板块列表

```bash
python3 backend/scripts/fill_sector_with_selenium.py --fetch-industry
```

### 3. 补全股票-板块关联数据

```bash
# 测试模式（只处理前3个板块）
python3 backend/scripts/fill_sector_with_selenium.py --fill-stock-sector --limit 3 --delay 2.0

# 完整模式（处理所有板块）
python3 backend/scripts/fill_sector_with_selenium.py --fill-stock-sector --delay 2.0
```

### 4. 从指定位置继续

```bash
# 从第10个板块开始
python3 backend/scripts/fill_sector_with_selenium.py --fill-stock-sector --start-from 10 --delay 2.0
```

## 参数说明

- `--fetch-industry`: 获取行业板块列表
- `--fill-stock-sector`: 补全股票-板块关联数据
- `--limit N`: 限制处理的板块数量（用于测试）
- `--delay N`: 每次请求之间的延迟（秒），建议 2.0-3.0
- `--start-from N`: 从第几个板块开始（用于断点续传）

## 注意事项

1. **资源消耗**：每个请求需要启动浏览器，资源消耗较大
2. **速度较慢**：相比直接 API 调用，速度较慢（每个板块约 3-5 秒）
3. **需要 Chrome**：需要安装 Chrome 浏览器
4. **ChromeDriver**：使用 `webdriver-manager` 自动管理，无需手动安装

## 数据格式

### 行业板块列表

```python
[
    {'sector_id': 'BK0420', 'name': '航空机场'},
    {'sector_id': 'BK0421', 'name': '铁路公路'},
    ...
]
```

### 板块成分股

```python
[
    {'code': '600519', 'name': '贵州茅台', 'market': 1},
    {'code': '000001', 'name': '平安银行', 'market': 0},
    ...
]
```

## 性能优化建议

1. **批量处理**：可以调整 `--limit` 参数，分批处理
2. **延迟设置**：根据网络情况调整 `--delay`，避免请求过快
3. **断点续传**：使用 `--start-from` 参数，从上次中断的位置继续

## 故障排查

### ChromeDriver 问题

如果遇到 ChromeDriver 相关错误：

```bash
# 使用 webdriver-manager 自动管理（推荐）
pip install webdriver-manager

# 或手动安装
brew install chromedriver
```

### 数据获取失败

1. 检查网络连接
2. 增加等待时间（调整 `time.sleep`）
3. 检查 API 参数是否正确

### 浏览器启动失败

1. 确保已安装 Chrome 浏览器
2. 检查 ChromeDriver 版本是否匹配
3. 尝试不使用无头模式（注释掉 `--headless`）查看错误信息

## 后续优化

1. **复用浏览器实例**：避免每个请求都启动新浏览器
2. **并发处理**：使用多线程/多进程处理多个板块
3. **缓存机制**：缓存已获取的数据，避免重复请求

