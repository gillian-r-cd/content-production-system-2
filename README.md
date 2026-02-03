# 内容生产系统 (Content Production System)

> AI Agent 驱动的商业内容生产平台

## 功能概述

- **意图分析**: Agent 提出探寻内容生产意图的关键问题
- **消费者调研**: DeepResearch 调研目标用户画像、痛点、价值点
- **内涵设计/生产**: 根据意图和调研设计并生产核心内容
- **外延设计/生产**: 针对不同渠道生成营销内容
- **消费者模拟**: 模拟真实用户体验并给予反馈
- **评估报告**: 全盘评估并提供修改建议

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Next.js 14 + TypeScript + Radix UI + Tiptap |
| 后端 | Python 3.11 + FastAPI + LangGraph |
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
│   │   ├── modules/        # 业务模块
│   │   ├── tools/          # LangGraph工具
│   │   ├── prompt_engine.py
│   │   ├── ai_client.py
│   │   └── orchestrator.py
│   ├── api/                # FastAPI路由
│   ├── tests/              # 测试
│   └── main.py
├── frontend/               # Next.js前端
├── data/                   # 数据库文件
└── .env                    # 环境变量
```

## 开发进度

- [x] Phase 0: 项目初始化
- [x] Phase 1: 数据模型
- [x] Phase 2: Prompt引擎
- [x] Phase 3: 工具模块
- [x] Phase 4: LangGraph Agent
- [x] Phase 5: FastAPI后端
- [x] Phase 6: Next.js前端
- [ ] Phase 7: 集成测试

## License

Private

