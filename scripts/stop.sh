#!/bin/bash
# scripts/stop.sh - 停止所有前后端服务
# 用法: ./scripts/stop.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'
DEFAULT_BACKEND_PORT=8000

read_backend_port() {
    local ENV_FILE="$PROJECT_DIR/backend/.env"
    if [ -f "$ENV_FILE" ]; then
        local PORT_VALUE
        PORT_VALUE=$(grep -E "^BACKEND_PORT=" "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d= -f2 | tr -d '[:space:]' | tr -d '"' | tr -d "'")
        if [[ "$PORT_VALUE" =~ ^[0-9]+$ ]]; then
            echo "$PORT_VALUE"
            return
        fi
    fi
    echo "$DEFAULT_BACKEND_PORT"
}

BACKEND_PORT=$(read_backend_port)

echo -e "${RED}⏹️  停止所有服务...${NC}"

# 杀掉后端 (目标端口)
BACKEND_PIDS=$(lsof -i :"$BACKEND_PORT" | grep LISTEN | awk '{print $2}' | sort -u)
if [ -n "$BACKEND_PIDS" ]; then
    echo "  停止后端进程: $BACKEND_PIDS"
    echo "$BACKEND_PIDS" | xargs kill -9 2>/dev/null || true
else
    echo "  后端未运行"
fi

# 杀掉前端 (端口 3000)
FRONTEND_PIDS=$(lsof -i :3000 | grep LISTEN | awk '{print $2}' | sort -u)
if [ -n "$FRONTEND_PIDS" ]; then
    echo "  停止前端进程: $FRONTEND_PIDS"
    echo "$FRONTEND_PIDS" | xargs kill -9 2>/dev/null || true
else
    echo "  前端未运行"
fi

# 额外清理
pkill -f "uvicorn main:app" 2>/dev/null || true
pkill -f "next-server" 2>/dev/null || true

echo -e "${GREEN}✅ 所有服务已停止${NC}"
