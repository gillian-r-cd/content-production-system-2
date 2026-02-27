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
| 后端 | Python 3.10+ + FastAPI + LangGraph |
| 数据库 | SQLite + SQLAlchemy |
| AI | OpenAI GPT-5.1 |

## 快速开始

### 前置条件

- Python 3.10+
- Node.js 18+
- npm

### 首次部署（两条命令）

```bash
# 1. 初始化：创建虚拟环境、安装所有依赖、生成 .env 模板
./scripts/setup.sh

# 2. 编辑 .env 填入你的 API Key
vim backend/.env

# 3. 启动前后端
./scripts/sync.sh start
```

### 日常更新（一条命令）

```bash
# 拉取最新代码 + 同步依赖 + 启动前后端
./scripts/sync.sh start
```

数据库 schema 和种子数据会在后端启动时自动同步，本地数据不受影响。

### 停止服务

```bash
./scripts/stop.sh
```

### 访问

- 前端: http://localhost:3000
- 后端API: http://localhost:8000
- API文档: http://localhost:8000/docs

### 手动部署（不使用脚本）

<details>
<summary>展开查看手动步骤</summary>

```bash
# 后端
cd backend
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# .\venv\Scripts\activate  # Windows
pip install -r requirements.txt
cp env_example.txt .env
# 编辑 .env 填入 API Key
python main.py

# 前端（另一个终端）
cd frontend
npm install
npm run dev
```

</details>

### 开始使用

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

## DeepResearch 评测层运行指南

> 说明：评测层不会在每次对话时自动执行，只有手动运行脚本时才会触发。

### 前置条件

- 后端依赖已安装（`pip install -r backend/requirements.txt`）
- 建议先运行并使用系统产生一些真实 `run_research` 轨迹（可选）

### 1) 生成/更新 20 条样本集

```bash
cd backend
python -m scripts.build_deepresearch_samples
```

输出文件：
- `backend/scripts/data/deepresearch_samples_20.json`

规则：
- 优先从本地数据库抽取真实 `run_research` 样本
- 不足 20 条会自动补 `pending_execution` 占位样本

### 2) 执行指标评测

```bash
cd backend
python -m scripts.eval_deepresearch_metrics --samples scripts/data/deepresearch_samples_20.json --output scripts/data/deepresearch_eval_report.json
```

仅评测已完成样本（忽略 pending）：

```bash
cd backend
python -m scripts.eval_deepresearch_metrics --samples scripts/data/deepresearch_samples_20.json --output scripts/data/deepresearch_eval_report.json --ignore-pending
```

输出文件：
- `backend/scripts/data/deepresearch_eval_report.json`

### 3) 会话迁移（可选）

如需先把历史消息回填到会话维度，再做样本抽取：

```bash
cd backend
python -m scripts.migrate_conversations --dry-run
python -m scripts.migrate_conversations --execute
```

## License

Private
