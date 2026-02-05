#!/bin/bash
# scripts/sync.sh - 同步代码并清理缓存
# 用法: ./scripts/sync.sh 或 bash scripts/sync.sh

set -e

echo "🔄 同步代码..."
git pull

echo "🧹 清理 Python 缓存..."
find backend -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find backend -name "*.pyc" -delete 2>/dev/null || true

echo "🧹 清理 Next.js 缓存..."
rm -rf frontend/.next 2>/dev/null || true

echo ""
echo "✅ 同步完成！"
echo ""
echo "后续步骤（如需）:"
echo "  cd backend && source venv/bin/activate && pip install -r requirements.txt"
echo "  cd frontend && npm install"
