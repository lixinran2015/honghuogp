#!/bin/bash
# 同时启动前后端服务

cd "$(dirname "$0")"

echo "🚀 启动量化交易系统（FastAPI + React）"
echo ""

# 启动后端（后台运行）
echo "📡 启动后端服务..."
cd backend
python run.py > ../logs/backend.log 2>&1 &
BACKEND_PID=$!
cd ..

# 等待后端启动
sleep 3

# 启动前端（Vue版本）
echo "🎨 启动前端服务..."
cd frontend-vue
if [ ! -d "node_modules" ]; then
    echo "📦 首次运行，正在安装前端依赖..."
    npm install
fi
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "✅ 服务已启动！"
echo "📍 后端API: http://localhost:8000"
echo "📍 前端界面: http://localhost:3000"
echo "📖 API文档: http://localhost:8000/docs"
echo ""
echo "按 Ctrl+C 停止所有服务"
echo ""

# 等待用户中断
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait

