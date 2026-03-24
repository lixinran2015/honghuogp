#!/bin/bash
# 启动前端服务（Vue版本）

cd "$(dirname "$0")/frontend-vue"
echo "🎨 启动Vue前端服务..."
echo "📍 前端地址: http://localhost:3000"
echo ""

if [ ! -d "node_modules" ]; then
    echo "📦 首次运行，正在安装依赖..."
    npm install
fi

npm run dev

