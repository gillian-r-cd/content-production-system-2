# 内容生产系统 (Content Production System)

> AI Agent 驱动的商业内容生产平台

## 功能概述

- **意图分析**: Agent 通过结构化提问深入理解内容生产意图
- **消费者调研**: DeepResearch 调研目标用户画像、痛点、价值点
- **内涵设计**: 基于意图和调研生成多套内容方案，支持手动调整字段与结构
- **内涵生产**: 按方案逐字段生成核心内容，支持自动/手动模式与字段依赖
- **外延设计/生产**: 针对不同渠道生成营销内容
- **内容评估 (Eval)**: 多模拟器（阅读/对话/探索/决策）+ 多维度 Grader 评分体系
- **灵活架构**: 支持传统阶段式流程与树形 ContentBlock 架构
- **字段模板**: 可复用的字段模板，包含预置 Eval 配置

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Next.js 16 + TypeScript + Radix UI + Tailwind CSS |
| 后端 | Python 3.14 + FastAPI + LangGraph |
| 数据库 | SQLite + SQLAlchemy |
| AI | OpenAI GPT-5.1 |

## 快速开始

### 1. 环境准备

```bash
# 克隆项目
cd 202601_content_production_system_2

# 复制环境变量 (进入backend目录)
cd backend
cp env_example.txt .env
# 编辑 .env 填写你的 OPENAI_API_KEY
```

### 2. 启动后端

```bash
cd backend

# 创建虚拟环境
python -m venv venv
.\venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# 安装依赖
pip install -r requirements.txt

# 启动服务
python main.py
```

### 3. 启动前端

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

### 4. 访问

- 前端: http://localhost:3000
- 后端API: http://localhost:8000
- API文档: http://localhost:8000/docs

### 5. 开始使用

📖 **首次使用请阅读 [使用者指南](docs/user_guide.md)**，包含：
- 后台设置步骤
- 创建第一个项目
- 内容生产流程详解
- 与 Agent 对话技巧
- 消费者模拟和评估

## 目录结构

```
├── docs/                    # 设计文档
├── backend/                 # Python后端
│   ├── core/               # 核心业务逻辑
│   │   ├── models/         # 数据模型
│   │   ├── tools/          # Eval引擎、模拟器等工具
│   │   ├── ai_client.py    # OpenAI API 封装
│   │   └── orchestrator.py # LangGraph Agent 编排器
│   ├── api/                # FastAPI路由
│   ├── scripts/            # 数据库初始化等脚本
│   ├── tests/              # E2E 测试
│   └── main.py
├── frontend/               # Next.js前端
│   ├── app/                # 页面路由
│   ├── components/         # React组件
│   └── lib/                # API客户端、工具函数
├── data/                   # SQLite 数据库文件
└── .env                    # 环境变量（需从 env_example.txt 复制）
```

## 开发进度

- [x] 项目初始化与数据模型
- [x] LangGraph Agent 编排器 + 意图路由
- [x] FastAPI 后端 API
- [x] Next.js 前端 (传统阶段式流程)
- [x] 灵活架构 (树形 ContentBlock)
- [x] 字段模板系统
- [x] Eval 系统 (多模拟器 + Grader)
- [x] E2E 集成测试

## License

Private
