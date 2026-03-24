#!/bin/bash

# 快速启动脚本

echo "=========================================="
echo "  量化交易系统 - 快速启动"
echo "=========================================="
echo ""

# 检查虚拟环境（项目使用 venv 目录）
if [ ! -d "venv" ]; then
    echo "创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
echo "激活虚拟环境..."
source venv/bin/activate

# 检查依赖
if [ ! -f "venv/.installed" ]; then
    echo "安装Python依赖..."
    pip install -r requirements.txt
    pip install -r backend/requirements.txt
    touch venv/.installed
fi

# 检查前端依赖
if [ ! -d "frontend-vue/node_modules" ]; then
    echo "安装前端依赖..."
    cd frontend-vue
    npm install
    cd ..
fi

# 启动系统
echo ""
echo "启动系统..."
./start_all.sh
