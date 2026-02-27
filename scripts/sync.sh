#!/bin/bash
# scripts/sync.sh - 同步代码、安装依赖、清理缓存、启动服务
# 功能: 日常更新一键脚本，拉取最新代码并同步依赖
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
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

sync_code() {
    echo -e "${BLUE}[1/4] 同步代码...${NC}"
    
    # 自动跟踪 GitHub 上的默认分支（发布分支）
    git fetch origin
    git remote set-head origin --auto 2>/dev/null || true
    RELEASE_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||')
    
    # 如果无法确定默认分支，回退到当前分支
    if [ -z "$RELEASE_BRANCH" ]; then
        RELEASE_BRANCH=$(git rev-parse --abbrev-ref HEAD)
    fi
    
    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
    
    if [ "$CURRENT_BRANCH" != "$RELEASE_BRANCH" ]; then
        echo -e "  ${YELLOW}发布分支已切换: $CURRENT_BRANCH -> $RELEASE_BRANCH${NC}"
        git checkout "$RELEASE_BRANCH"
    fi
    
    # 确保 upstream tracking 正确（防止 git pull 报 no tracking 错误）
    git branch --set-upstream-to="origin/$RELEASE_BRANCH" "$RELEASE_BRANCH" 2>/dev/null || true
    
    # 自动暂存本地变更（自动生成的文件如 .db-wal、next-env.d.ts 等）
    # 防止 git pull 因工作区脏文件而失败
    STASHED=false
    if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
        echo -e "  ${YELLOW}检测到本地变更，自动暂存...${NC}"
        git stash push -m "sync.sh auto-stash $(date +%Y%m%d-%H%M%S)" --quiet
        STASHED=true
    fi
    
    git pull origin "$RELEASE_BRANCH"
    
    # 恢复暂存的本地变更
    if [ "$STASHED" = true ]; then
        echo -e "  ${YELLOW}恢复本地变更...${NC}"
        git stash pop --quiet 2>/dev/null || {
            echo -e "  ${YELLOW}自动恢复冲突，已保留在 git stash 中（不影响使用）${NC}"
        }
    fi
    
    echo -e "${BLUE}[2/4] 安装/更新后端依赖...${NC}"
    cd "$PROJECT_DIR/backend"
    if [ ! -d "venv" ]; then
        echo -e "${YELLOW}  venv 不存在，请先运行 ./scripts/setup.sh${NC}"
        exit 1
    fi
    
    # 检查 venv 中的 Python 版本是否 >= 3.10，不满足则自动重建
    VENV_PY_VER=$(venv/bin/python3 --version 2>&1 | awk '{print $2}')
    VENV_PY_MINOR=$(echo "$VENV_PY_VER" | cut -d. -f2)
    if [ "$VENV_PY_MINOR" -lt 10 ] 2>/dev/null; then
        echo -e "  ${YELLOW}venv 中的 Python ($VENV_PY_VER) 版本过低，自动重建...${NC}"
        rm -rf venv
        # 查找可用的 Python >= 3.10
        REBUILD_PY=""
        for candidate in python3 python3.12 python3.11 python3.10; do
            if command -v "$candidate" &> /dev/null; then
                CAND_MINOR=$("$candidate" --version 2>&1 | awk '{print $2}' | cut -d. -f2)
                if [ "$CAND_MINOR" -ge 10 ] 2>/dev/null; then
                    REBUILD_PY="$candidate"
                    break
                fi
            fi
        done
        if [ -z "$REBUILD_PY" ]; then
            echo -e "  ${RED}未找到 Python >= 3.10，请先安装: brew install python@3.12${NC}"
            exit 1
        fi
        echo -e "  ${YELLOW}使用 $REBUILD_PY 重建 venv...${NC}"
        "$REBUILD_PY" -m venv venv
    fi
    
    source venv/bin/activate
    pip install -r requirements.txt --quiet
    deactivate
    cd "$PROJECT_DIR"
    
    echo -e "${BLUE}[3/4] 安装/更新前端依赖...${NC}"
    cd "$PROJECT_DIR/frontend"
    npm install --silent
    cd "$PROJECT_DIR"
    
    echo -e "${BLUE}[4/4] 清理缓存...${NC}"
    find backend -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find backend -name "*.pyc" -delete 2>/dev/null || true
    # 注意: 不删除 frontend/.next，保留编译缓存以加速前端启动
    
    echo -e "${GREEN}同步完成！数据库 schema 和种子数据会在后端启动时自动同步。${NC}"
}

wait_for_port() {
    # 用法: wait_for_port 端口号 PID 服务名 最大等待秒数
    local PORT=$1 PID=$2 NAME=$3 MAX=$4
    local COUNT=0
    while [ $COUNT -lt $MAX ]; do
        if lsof -i :"$PORT" | grep -q LISTEN 2>/dev/null; then
            return 0  # 成功
        fi
        if ! kill -0 "$PID" 2>/dev/null; then
            return 1  # 进程已死
        fi
        sleep 2
        COUNT=$((COUNT + 2))
    done
    return 2  # 超时
}

start_services() {
    echo ""
    echo -e "${BLUE}🚀 启动服务...${NC}"
    
    # 杀掉占用端口的进程
    echo "  清理端口 8000 和 3000..."
    lsof -i :8000 | grep LISTEN | awk '{print $2}' | xargs kill -9 2>/dev/null || true
    lsof -i :3000 | grep LISTEN | awk '{print $2}' | xargs kill -9 2>/dev/null || true
    sleep 1
    
    # ===== 启动后端 =====
    echo -e "  ${BLUE}🐍 启动后端 (localhost:8000)...${NC}"
    cd "$PROJECT_DIR/backend"
    source venv/bin/activate
    python main.py > /tmp/backend.log 2>&1 &
    BACKEND_PID=$!
    echo "     后端 PID: $BACKEND_PID"
    
    # 等待后端真正就绪（检测端口 8000，最多等 60 秒）
    echo "  ⏳ 等待后端启动..."
    wait_for_port 8000 $BACKEND_PID "后端" 60
    BACKEND_STATUS=$?
    
    if [ $BACKEND_STATUS -eq 1 ]; then
        echo -e "  ${RED}❌ 后端启动失败！错误日志:${NC}"
        echo -e "${RED}-------------------------------------------${NC}"
        tail -30 /tmp/backend.log
        echo -e "${RED}-------------------------------------------${NC}"
        echo -e "  ${YELLOW}完整日志: cat /tmp/backend.log${NC}"
        echo -e "  ${YELLOW}请检查 backend/.env 中的 API Key 配置是否正确。${NC}"
        exit 1
    elif [ $BACKEND_STATUS -eq 2 ]; then
        echo -e "  ${YELLOW}⚠️  后端启动超时，可能仍在初始化中...${NC}"
    else
        echo -e "  ${GREEN}✅ 后端已就绪${NC}"
    fi
    
    # ===== 启动前端 =====
    echo -e "  ${BLUE}⚛️  启动前端 (localhost:3000)...${NC}"
    cd "$PROJECT_DIR/frontend"
    npm run dev > /tmp/frontend.log 2>&1 &
    FRONTEND_PID=$!
    echo "     前端 PID: $FRONTEND_PID"
    
    # 等待前端真正就绪（检测端口 3000，最多等 120 秒）
    echo "  ⏳ 等待前端编译完成（首次可能需要 30~60 秒）..."
    wait_for_port 3000 $FRONTEND_PID "前端" 120
    FRONTEND_STATUS=$?
    
    if [ $FRONTEND_STATUS -eq 1 ]; then
        echo -e "  ${RED}❌ 前端启动失败！错误日志:${NC}"
        echo -e "${RED}-------------------------------------------${NC}"
        tail -30 /tmp/frontend.log
        echo -e "${RED}-------------------------------------------${NC}"
        echo -e "  ${YELLOW}完整日志: cat /tmp/frontend.log${NC}"
        exit 1
    elif [ $FRONTEND_STATUS -eq 2 ]; then
        echo -e "  ${YELLOW}⚠️  前端编译超时，可能仍在编译中。请稍后刷新浏览器。${NC}"
    else
        echo -e "  ${GREEN}✅ 前端已就绪${NC}"
    fi
    
    echo ""
    echo -e "${GREEN}=========================================="
    echo -e "  ✅ 服务已启动！"
    echo -e "==========================================${NC}"
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
