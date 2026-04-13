#!/bin/bash
set -e

echo "=== 红火量化 Phase 1 部署脚本 ==="

# 检查必要文件
if [ ! -f "../../../.env" ]; then
    echo "错误：未找到 ../../../.env 文件，请先配置数据库密码等环境变量"
    exit 1
fi

if [ ! -f "../../../config.json" ]; then
    echo "警告：未找到 ../../../config.json，部分功能（如 Tushare）可能不可用"
fi

# 构建并启动
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up --build -d

# 等待后端启动
echo "等待后端服务启动..."
sleep 5

for i in {1..10}; do
    if curl -s http://localhost:8000/docs > /dev/null; then
        echo "后端服务已就绪: http://localhost:8000"
        break
    fi
    echo "等待中... ($i/10)"
    sleep 3
done

# 检查健康状态
BACKEND_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/docs || echo "000")
if [ "$BACKEND_HEALTH" != "200" ]; then
    echo "错误：后端服务未正常启动，请检查日志: docker logs honghuo-backend"
    exit 1
fi

echo "=== 部署完成 ==="
echo "前端: http://localhost"
echo "后端 API: http://localhost:8000/docs"
