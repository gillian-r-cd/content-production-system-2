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

# 检查 git
if ! command -v git &> /dev/null; then
    echo -e "${RED}  错误: 未找到 git。${NC}"
    if [[ "$(uname)" == "Darwin" ]]; then
        echo -e "${YELLOW}  macOS 用户请先安装 Xcode Command Line Tools:${NC}"
        echo -e "${YELLOW}    xcode-select --install${NC}"
        echo -e "${YELLOW}  安装完成后重新打开终端，再运行此脚本。${NC}"
    else
        echo -e "${YELLOW}  请先安装 git，然后重新运行此脚本。${NC}"
    fi
    exit 1
fi
echo "  git: $(git --version | awk '{print $3}')"

# 检查 Python >= 3.10
# 策略: 按优先级逐个尝试 python3 -> python3.12 -> python3.11 -> python3.10 -> python
# 找到第一个版本 >= 3.10 的就用它（解决 macOS 系统 python3 是 3.9 但 Homebrew 装了 3.12 的情况）
PYTHON_CMD=""
for candidate in python3 python3.12 python3.11 python3.10 python; do
    if command -v "$candidate" &> /dev/null; then
        VER=$("$candidate" --version 2>&1 | awk '{print $2}')
        MAJOR=$(echo "$VER" | cut -d. -f1)
        MINOR=$(echo "$VER" | cut -d. -f2)
        if [ "$MAJOR" -ge 3 ] 2>/dev/null && [ "$MINOR" -ge 10 ] 2>/dev/null; then
            PYTHON_CMD="$candidate"
            PYTHON_VERSION="$VER"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    # 显示当前 python3 版本（如果有）帮助用户理解问题
    if command -v python3 &> /dev/null; then
        CURRENT_VER=$(python3 --version 2>&1 | awk '{print $2}')
        echo -e "${RED}  错误: 当前 Python 版本 ($CURRENT_VER) 过低，本项目需要 Python 3.10 或更高版本。${NC}"
    else
        echo -e "${RED}  错误: 未找到 Python，本项目需要 Python 3.10 或更高版本。${NC}"
    fi
    echo -e "${YELLOW}  推荐使用 Homebrew 安装: brew install python@3.12${NC}"
    echo -e "${YELLOW}  安装后重新运行此脚本即可。${NC}"
    exit 1
fi

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
