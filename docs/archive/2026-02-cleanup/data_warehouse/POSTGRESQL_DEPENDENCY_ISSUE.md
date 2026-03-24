# PostgreSQL依赖安装问题

## 当前状态

- ✅ **SQLAlchemy** 已成功安装（版本 2.0.44）
- ❌ **psycopg2-binary** 因网络问题未安装
- ✅ **后端服务可以正常启动**（会回退到文件数据仓库）

## 影响

- PostgreSQL数据仓库功能暂时不可用
- 系统会自动回退到文件数据仓库（`data_warehouse/` 目录）
- 其他功能（实时查询、推荐选股等）正常工作

## 解决方案

### 方法1：手动安装（推荐）

在网络条件良好时，运行：

```bash
source .venv/bin/activate
pip install psycopg2-binary
```

如果仍然超时，可以尝试：

```bash
# 使用阿里云镜像
pip install -i https://mirrors.aliyun.com/pypi/simple/ psycopg2-binary

# 或增加超时时间
pip install --timeout 600 psycopg2-binary
```

### 方法2：使用conda（如果已安装）

```bash
conda install -c conda-forge psycopg2
```

### 方法3：暂时使用文件数据仓库

如果PostgreSQL依赖暂时无法安装，系统会自动使用文件数据仓库，功能不受影响。

## 验证安装

安装完成后，运行：

```bash
python3 -c "import psycopg2; print('✅ psycopg2安装成功')"
```

然后重启后端服务，PostgreSQL数据仓库功能会自动启用。

## 当前启动方式

即使没有psycopg2-binary，后端也可以正常启动：

```bash
cd /Users/wuyanze/quantitative_trading
source .venv/bin/activate
python -m uvicorn backend.app:app --host 0.0.0.0 --port 8888
```

系统会显示警告信息，但会继续使用文件数据仓库。

