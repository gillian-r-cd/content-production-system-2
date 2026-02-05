#!/bin/bash
# scripts/sync.sh - 同步代码、清理缓存、启动服务
# 用法: 
#   ./scripts/sync.sh        - 只同步和清理
#   ./scripts/sync.sh start  - 同步后启动前后端
#   ./scripts/sync.sh dev    - 只启动前后端（不同步）

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

sync_code() {
    echo -e "${BLUE}🔄 同步代码...${NC}"
    git pull
    
    echo -e "${BLUE}🧹 清理 Python 缓存...${NC}"
    find backend -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find backend -name "*.pyc" -delete 2>/dev/null || true
    
    echo -e "${BLUE}🧹 清理 Next.js 缓存...${NC}"
    rm -rf frontend/.next 2>/dev/null || true
    
    echo -e "${GREEN}✅ 同步完成！${NC}"
}

start_services() {
    echo ""
    echo -e "${BLUE}🚀 启动服务...${NC}"
    
    # 杀掉占用端口的进程
    echo "  清理端口 8000 和 3000..."
    lsof -i :8000 | grep LISTEN | awk '{print $2}' | xargs kill -9 2>/dev/null || true
    lsof -i :3000 | grep LISTEN | awk '{print $2}' | xargs kill -9 2>/dev/null || true
    sleep 1
    
    # 启动后端
    echo -e "  ${BLUE}🐍 启动后端 (localhost:8000)...${NC}"
    cd "$PROJECT_DIR/backend"
    source venv/bin/activate
    python main.py > /tmp/backend.log 2>&1 &
    BACKEND_PID=$!
    echo "     后端 PID: $BACKEND_PID"
    
    # 等待后端启动
    sleep 3
    
    # 启动前端
    echo -e "  ${BLUE}⚛️  启动前端 (localhost:3000)...${NC}"
    cd "$PROJECT_DIR/frontend"
    npm run dev > /tmp/frontend.log 2>&1 &
    FRONTEND_PID=$!
    echo "     前端 PID: $FRONTEND_PID"
    
    # 等待前端启动
    sleep 3
    
    echo ""
    echo -e "${GREEN}✅ 服务已启动！${NC}"
    echo ""
    echo "  🌐 前端: http://localhost:3000"
    echo "  🔌 后端: http://localhost:8000"
    echo "  📝 后端日志: tail -f /tmp/backend.log"
    echo "  📝 前端日志: tail -f /tmp/frontend.log"
    echo ""
    echo "  停止服务: kill $BACKEND_PID $FRONTEND_PID"
}

# 主逻辑
case "${1:-sync}" in
    start)
        sync_code
        start_services
        ;;
    dev)
        start_services
        ;;
    sync|"")
        sync_code
        echo ""
        echo "提示: 运行 './scripts/sync.sh start' 可同时启动前后端"
        ;;
    *)
        echo "用法: $0 [sync|start|dev]"
        echo "  sync  - 只同步代码和清理缓存（默认）"
        echo "  start - 同步后启动前后端"
        echo "  dev   - 只启动前后端（不同步）"
        exit 1
        ;;
esac
