#!/bin/bash
# scripts/restart.sh - 杀掉所有前后端进程并重启
# 用法: ./scripts/restart.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔄 重启前后端服务...${NC}"
echo ""

# ===== 步骤1: 杀掉所有占用端口的进程 =====
echo -e "${YELLOW}⏹️  停止现有服务...${NC}"

# 杀掉后端 (端口 8000)
BACKEND_PIDS=$(lsof -i :8000 | grep LISTEN | awk '{print $2}' | sort -u)
if [ -n "$BACKEND_PIDS" ]; then
    echo "  杀掉后端进程: $BACKEND_PIDS"
    echo "$BACKEND_PIDS" | xargs kill -9 2>/dev/null || true
else
    echo "  后端未运行"
fi

# 杀掉前端 (端口 3000)
FRONTEND_PIDS=$(lsof -i :3000 | grep LISTEN | awk '{print $2}' | sort -u)
if [ -n "$FRONTEND_PIDS" ]; then
    echo "  杀掉前端进程: $FRONTEND_PIDS"
    echo "$FRONTEND_PIDS" | xargs kill -9 2>/dev/null || true
else
    echo "  前端未运行"
fi

# 额外杀掉可能残留的 node 和 python 相关进程
pkill -f "uvicorn main:app" 2>/dev/null || true
pkill -f "next-server" 2>/dev/null || true

sleep 2

# ===== 步骤2: 启动后端 =====
echo ""
echo -e "${BLUE}🐍 启动后端 (localhost:8000)...${NC}"
cd "$PROJECT_DIR/backend"
source venv/bin/activate
nohup python main.py > /tmp/backend.log 2>&1 &
BACKEND_PID=$!
echo "  后端 PID: $BACKEND_PID"

# 等待后端启动
sleep 3

# 检查后端是否启动成功
if curl -s http://localhost:8000/api/projects/ > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓ 后端启动成功${NC}"
else
    echo -e "  ${YELLOW}⚠ 后端可能还在启动中...${NC}"
fi

# ===== 步骤3: 启动前端 =====
echo ""
echo -e "${BLUE}⚛️  启动前端 (localhost:3000)...${NC}"
cd "$PROJECT_DIR/frontend"
nohup npm run dev > /tmp/frontend.log 2>&1 &
FRONTEND_PID=$!
echo "  前端 PID: $FRONTEND_PID"

# 等待前端启动
sleep 4

echo ""
echo -e "${GREEN}✅ 重启完成！${NC}"
echo ""
echo "  🌐 前端: http://localhost:3000"
echo "  🔌 后端: http://localhost:8000"
echo ""
echo "  📝 查看日志:"
echo "     tail -f /tmp/backend.log   # 后端日志"
echo "     tail -f /tmp/frontend.log  # 前端日志"
echo ""
echo "  🛑 停止服务:"
echo "     kill $BACKEND_PID $FRONTEND_PID"
echo "     或: ./scripts/stop.sh"
