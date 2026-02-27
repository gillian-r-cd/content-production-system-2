#!/bin/bash
# scripts/setup.sh - 首次部署一键初始化脚本
# 功能: 创建 venv、安装依赖、生成 .env 模板、安装前端依赖
# 用法: ./scripts/setup.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo ""
echo "=========================================="
echo "  内容生产系统 - 首次部署初始化"
echo "=========================================="
echo ""

# ===== 步骤 1: 检查前置依赖 =====
echo -e "${BLUE}[1/4] 检查前置依赖...${NC}"

# 检查 Python 3
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo -e "${RED}错误: 未找到 Python。请先安装 Python 3.9 或更高版本。${NC}"
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
echo "  Python: $PYTHON_VERSION ($PYTHON_CMD)"

# 检查 Node.js
if ! command -v node &> /dev/null; then
    echo -e "${RED}错误: 未找到 Node.js。请先安装 Node.js 18 或更高版本。${NC}"
    exit 1
fi
echo "  Node.js: $(node --version)"

# 检查 npm
if ! command -v npm &> /dev/null; then
    echo -e "${RED}错误: 未找到 npm。请先安装 npm。${NC}"
    exit 1
fi
echo "  npm: $(npm --version)"

echo ""

# ===== 步骤 2: 后端初始化 =====
echo -e "${BLUE}[2/4] 初始化后端...${NC}"

cd "$PROJECT_DIR/backend"

# 创建 venv（如果不存在）
if [ ! -d "venv" ]; then
    echo "  创建 Python 虚拟环境..."
    $PYTHON_CMD -m venv venv
    echo "  虚拟环境已创建"
else
    echo "  虚拟环境已存在，跳过创建"
fi

# 安装依赖
echo "  安装 Python 依赖..."
source venv/bin/activate
pip install -r requirements.txt --quiet
deactivate

echo ""

# ===== 步骤 3: 环境变量配置 =====
echo -e "${BLUE}[3/4] 配置环境变量...${NC}"

if [ -f ".env" ]; then
    echo "  .env 文件已存在，跳过（不会覆盖你的配置）"
else
    cp env_example.txt .env
    echo "  已从 env_example.txt 生成 .env 文件"
    echo -e "${YELLOW}  >>> 重要: 请编辑 backend/.env 填入你的 API Key <<<${NC}"
fi

cd "$PROJECT_DIR"
echo ""

# ===== 步骤 4: 前端初始化 =====
echo -e "${BLUE}[4/4] 初始化前端...${NC}"

cd "$PROJECT_DIR/frontend"
echo "  安装前端依赖..."
npm install --silent
cd "$PROJECT_DIR"

echo ""
echo "=========================================="
echo -e "${GREEN}  初始化完成！${NC}"
echo "=========================================="
echo ""
echo "  接下来请："
echo ""
if [ ! -f "$PROJECT_DIR/backend/.env" ] || grep -q "sk-xxxx" "$PROJECT_DIR/backend/.env" 2>/dev/null; then
    echo "  1. 编辑 backend/.env 填入你的 API Key:"
    echo "     vim backend/.env"
    echo ""
    echo "  2. 启动服务:"
    echo "     ./scripts/sync.sh start"
else
    echo "  启动服务:"
    echo "     ./scripts/sync.sh start"
fi
echo ""
echo "  服务启动后访问:"
echo "     前端: http://localhost:3000"
echo "     后端: http://localhost:8000"
echo ""
echo "  日常更新（拉取代码 + 同步依赖 + 启动）:"
echo "     ./scripts/sync.sh start"
echo ""
echo "  停止服务:"
echo "     ./scripts/stop.sh"
echo ""
