#!/bin/bash
# 启动后端服务

cd "$(dirname "$0")/backend"

# 检查端口8000是否被占用
PORT=8000
PID=$(lsof -ti:$PORT 2>/dev/null)

if [ ! -z "$PID" ]; then
    echo "⚠️  检测到端口 $PORT 已被占用 (PID: $PID)"
    echo "🔄 正在停止占用端口的进程..."
    kill -9 $PID 2>/dev/null
    sleep 1
    echo "✅ 端口已释放"
    echo ""
fi

echo "🚀 启动FastAPI后端服务..."
echo "📍 后端地址: http://localhost:8000"
echo "📖 API文档: http://localhost:8000/docs"
echo ""

python run.py

