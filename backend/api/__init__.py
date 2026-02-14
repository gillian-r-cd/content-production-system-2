# backend/api/__init__.py
# 功能: API模块入口
# 注意: 各路由模块在 main.py 中按需导入注册，这里不再做 eager import
#       避免 agent -> orchestrator -> langgraph 的链式依赖问题

"""
FastAPI 路由模块
"""
