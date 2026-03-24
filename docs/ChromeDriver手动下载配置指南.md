# ChromeDriver 手动下载和配置指南

## 方法一：手动下载并配置到 PATH（推荐）

### 步骤 1：查看 Chrome 版本

1. 打开 Chrome 浏览器
2. 在地址栏输入：`chrome://version/`
3. 查看版本号，例如：`142.0.7444.175`

### 步骤 2：下载对应版本的 ChromeDriver

#### 对于 Chrome 115 及以上版本（推荐方式）

访问 Chrome for Testing 网站：
```
https://googlechromelabs.github.io/chrome-for-testing/
```

或者直接下载链接（Windows 64位）：
```
https://storage.googleapis.com/chrome-for-testing-public/142.0.7444.175/win64/chromedriver-win64.zip
```

**注意**：将 `142.0.7444.175` 替换为您实际的 Chrome 版本号。

#### 对于 Chrome 114 及以下版本

访问旧版下载地址：
```
http://chromedriver.storage.googleapis.com/index.html
```

### 步骤 3：解压并配置

1. **解压下载的 zip 文件**，找到 `chromedriver.exe`

2. **配置方式（任选一种）**：

   **方式 A：放到 Chrome 安装目录**
   - 将 `chromedriver.exe` 复制到：
     ```
     C:\Program Files\Google\Chrome\Application\
     ```
   - 或者：
     ```
     C:\Program Files (x86)\Google\Chrome\Application\
     ```

   **方式 B：放到项目目录（推荐）**
   - 在项目根目录创建 `drivers` 文件夹：
     ```
     d:\honghuo\honghuogp\drivers\
     ```
   - 将 `chromedriver.exe` 放到该目录

   **方式 C：添加到系统 PATH**
   - 创建一个专门的目录，例如：`D:\tools\chromedriver\`
   - 将 `chromedriver.exe` 放到该目录
   - 添加到系统环境变量 PATH：
     1. 右键"此电脑" → "属性" → "高级系统设置"
     2. 点击"环境变量"
     3. 在"系统变量"中找到 `Path`，点击"编辑"
     4. 点击"新建"，添加 `D:\tools\chromedriver\`
     5. 确定保存

### 步骤 4：验证安装

打开 PowerShell，运行：
```powershell
chromedriver --version
```

如果显示版本号，说明配置成功。

---

## 方法二：在代码中指定 ChromeDriver 路径

如果不想配置 PATH，可以在代码中直接指定 ChromeDriver 的路径。

### 修改代码支持手动指定路径

在 `guba_popularity_crawler.py` 中，可以这样修改：

```python
import os
from pathlib import Path

# 尝试从多个位置查找 chromedriver
def find_chromedriver():
    """查找 chromedriver.exe 的位置"""
    possible_paths = [
        # 1. 项目目录下的 drivers 文件夹
        Path(__file__).parent.parent.parent.parent / "drivers" / "chromedriver.exe",
        # 2. Chrome 安装目录
        Path("C:/Program Files/Google/Chrome/Application/chromedriver.exe"),
        Path("C:/Program Files (x86)/Google/Chrome/Application/chromedriver.exe"),
        # 3. 系统 PATH 中的 chromedriver
        "chromedriver.exe",
    ]
    
    for path in possible_paths:
        if isinstance(path, Path):
            if path.exists():
                return str(path)
        else:
            # 尝试从 PATH 中查找
            import shutil
            chromedriver_path = shutil.which(path)
            if chromedriver_path:
                return chromedriver_path
    
    return None

# 在启动浏览器时使用
chromedriver_path = find_chromedriver()
if chromedriver_path:
    service = Service(chromedriver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)
else:
    # 回退到 webdriver-manager 或系统默认
    ...
```

---

## 快速下载脚本（PowerShell）

创建一个 PowerShell 脚本来自动下载：

```powershell
# download_chromedriver.ps1
$chromeVersion = (Get-Item (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe' -ErrorAction SilentlyContinue).'(Default)' -ErrorAction SilentlyContinue).VersionInfo.FileVersion
$majorVersion = $chromeVersion.Split('.')[0]

Write-Host "检测到 Chrome 版本: $chromeVersion"

# Chrome 115+ 使用新的下载地址
if ([int]$majorVersion -ge 115) {
    $url = "https://storage.googleapis.com/chrome-for-testing-public/$chromeVersion/win64/chromedriver-win64.zip"
    Write-Host "下载地址: $url"
    
    $zipPath = "$env:TEMP\chromedriver-win64.zip"
    $extractPath = "$env:TEMP\chromedriver"
    $targetPath = ".\drivers"
    
    # 创建目标目录
    New-Item -ItemType Directory -Force -Path $targetPath | Out-Null
    
    # 下载
    Write-Host "正在下载..."
    Invoke-WebRequest -Uri $url -OutFile $zipPath
    
    # 解压
    Write-Host "正在解压..."
    Expand-Archive -Path $zipPath -DestinationPath $extractPath -Force
    
    # 复制到目标目录
    Copy-Item "$extractPath\chromedriver-win64\chromedriver.exe" -Destination "$targetPath\chromedriver.exe" -Force
    
    Write-Host "✅ ChromeDriver 已下载到: $targetPath\chromedriver.exe"
    
    # 清理临时文件
    Remove-Item $zipPath -Force
    Remove-Item $extractPath -Recurse -Force
} else {
    Write-Host "Chrome 版本过低，请手动下载"
}
```

---

## 常见问题

### Q: 如何查看 ChromeDriver 版本是否匹配？

A: 运行以下命令：
```powershell
chromedriver --version
chrome --version
```

两个版本号的主要版本号（第一个数字）应该相同。

### Q: 下载后仍然报错？

A: 检查以下几点：
1. ChromeDriver 版本是否与 Chrome 版本匹配
2. ChromeDriver 是否在 PATH 中，或路径是否正确
3. 文件权限是否正确（Windows 可能需要管理员权限）

### Q: 可以使用旧版本的 ChromeDriver 吗？

A: 不推荐。ChromeDriver 版本必须与 Chrome 浏览器版本匹配，否则可能出现兼容性问题。

---

## 推荐配置

**最简单的方式**：
1. 在项目根目录创建 `drivers` 文件夹
2. 下载对应版本的 `chromedriver.exe` 放到该文件夹
3. 修改代码支持从该路径加载（见方法二）

这样既不需要修改系统 PATH，也便于版本管理。
