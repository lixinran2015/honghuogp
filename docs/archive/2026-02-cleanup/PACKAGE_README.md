# 系统打包说明

## 使用方法

运行打包脚本：

```bash
./package_system.sh
```

## 打包内容

### ✅ 包含的内容

1. **核心代码**
   - `backend/` - 后端代码（排除缓存和日志）
   - `frontend-vue/` - 前端代码（排除node_modules）
   - `data_warehouse/` - 数据仓库代码
   - `config/` - 配置文件
   - `utils/` - 工具函数

2. **配置文件**
   - `config.json` - 主配置文件
   - `requirements.txt` - Python依赖
   - `frontend-vue/package.json` - 前端依赖

3. **启动脚本**
   - `start_all.sh` - 启动前后端
   - `start_backend.sh` - 启动后端
   - `start_frontend.sh` - 启动前端
   - `quick_start.sh` - 快速启动脚本

4. **数据库备份**
   - `database_backup.sql` - PostgreSQL数据库完整备份

5. **文档**
   - `INSTALL.md` - 详细的安装指南
   - `README.md` - 项目说明
   - `docs/` - 技术文档

### ❌ 排除的内容

以下内容不会被打包（用户需要自行生成）：

- `node_modules/` - 前端依赖（运行 `npm install` 安装）
- `__pycache__/` - Python缓存文件
- `.venv/` - Python虚拟环境
- `logs/` - 日志文件
- `archive/` - 归档文件
- `*.log` - 日志文件
- `.git/` - Git版本控制
- `data_cache/` - 临时缓存
- `backend/data_cache/` - 后端缓存
- `backend/logs/` - 后端日志

## 打包输出

脚本会生成：

1. **打包目录**: `quantitative_trading_package_YYYYMMDD_HHMMSS/`
2. **压缩文件**: `quantitative_trading_package_YYYYMMDD_HHMMSS.tar.gz`

## 数据库备份说明

脚本会自动尝试备份PostgreSQL数据库：

- 数据库名: `quantitative_trading`
- 备份文件: `database_backup.sql`
- 备份命令: `pg_dump -d quantitative_trading > database_backup.sql`

如果自动备份失败，请手动执行：

```bash
pg_dump -d quantitative_trading > database_backup.sql
```

或使用postgres用户：

```bash
pg_dump -U postgres -d quantitative_trading > database_backup.sql
```

## 用户安装步骤

用户收到打包文件后，需要：

1. **解压文件**
   ```bash
   tar -xzf quantitative_trading_package_*.tar.gz
   cd quantitative_trading_package_*
   ```

2. **安装系统依赖**
   - PostgreSQL 14+
   - Python 3.8+
   - Node.js 16+

3. **恢复数据库**
   ```bash
   createdb quantitative_trading
   psql -d quantitative_trading < database_backup.sql
   ```

4. **安装Python依赖**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   pip install -r backend/requirements.txt
   ```

5. **安装前端依赖**
   ```bash
   cd frontend-vue
   npm install
   cd ..
   ```

6. **配置数据库连接**
   - 编辑 `data_warehouse/config.py`
   - 或设置环境变量 `DATABASE_URL`

7. **启动系统**
   ```bash
   ./start_all.sh
   ```

或使用快速启动脚本（自动安装依赖）：

```bash
./quick_start.sh
```

## 注意事项

1. **API密钥**: `config.json` 中包含的API密钥需要用户自行配置或替换
2. **数据库密码**: 如果数据库有密码，需要在 `data_warehouse/config.py` 中配置
3. **网络要求**: 系统需要访问互联网以获取股票数据
4. **数据更新**: 首次运行后，需要在"数据管理"页面触发数据更新

## 文件大小估算

- 代码文件: ~50-100 MB
- 数据库备份: 取决于数据量（通常 100MB - 1GB）
- 压缩后: 通常为原大小的 30-50%

## 验证打包

打包完成后，可以验证：

```bash
# 查看打包内容
tar -tzf quantitative_trading_package_*.tar.gz | head -20

# 检查关键文件
tar -xzf quantitative_trading_package_*.tar.gz
ls -la quantitative_trading_package_*/backend/
ls -la quantitative_trading_package_*/frontend-vue/
ls -la quantitative_trading_package_*/database_backup.sql
```

