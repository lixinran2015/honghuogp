# 安装PostgreSQL依赖

如果遇到网络问题导致 `sqlalchemy` 和 `psycopg2-binary` 安装失败，可以尝试以下方法：

## 方法1：使用国内镜像源（推荐）

```bash
source .venv/bin/activate
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple sqlalchemy psycopg2-binary
```

或者使用阿里云镜像：

```bash
pip install -i https://mirrors.aliyun.com/pypi/simple/ sqlalchemy psycopg2-binary
```

## 方法2：增加超时时间

```bash
pip install --timeout 300 sqlalchemy psycopg2-binary
```

## 方法3：分步安装

```bash
# 先安装sqlalchemy
pip install sqlalchemy

# 再安装psycopg2-binary
pip install psycopg2-binary
```

## 方法4：使用conda（如果已安装conda）

```bash
conda install -c conda-forge sqlalchemy psycopg2
```

## 验证安装

安装完成后，运行以下命令验证：

```bash
python3 -c "import sqlalchemy; import psycopg2; print('✅ 所有依赖已安装')"
```

## 注意

- 如果PostgreSQL依赖未安装，后端仍然可以启动，但会回退到文件数据仓库
- PostgreSQL数据仓库功能需要这些依赖才能正常工作
- 建议在网络条件良好时完成安装

