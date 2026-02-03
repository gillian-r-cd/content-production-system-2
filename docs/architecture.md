# 系统架构文档
# 创建时间: 20260202
# 功能: 定义系统整体架构、技术栈、数据流向

## 技术栈

| 层级 | 技术选型 | 说明 |
|------|----------|------|
| 前端框架 | Next.js 14 (App Router) | SSR支持、文件路由、API Routes |
| 前端UI | Radix UI + Tailwind CSS | 无障碍组件、原子CSS |
| 富文本编辑 | Tiptap | 所见即所得、可扩展 |
| 后端框架 | FastAPI | 异步支持、自动文档、类型安全 |
| Agent框架 | LangGraph | 状态图、人机协作、可视化 |
| 数据库 | SQLite + SQLAlchemy | 零配置、JSON支持、易迁移 |
| 大模型 | OpenAI GPT-4 | 用户提供API Key |

## 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    Next.js 14 Frontend                       │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ 左栏进度  │  │  中栏编辑器   │  │  右栏Agent对话          │ │
│  │ (React)  │  │ (Tiptap)     │  │  (SSE Streaming)      │ │
│  └──────────┘  └──────────────┘  └────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │ HTTP + SSE
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Backend                           │
│  ┌───────────────┐  ┌────────────────┐  ┌────────────────┐  │
│  │ LangGraph Agent│  │ Prompt Engine  │  │ Stream Manager │  │
│  │ (核心编排)     │  │ (Golden Context)│  │ (SSE输出)      │  │
│  └───────────────┘  └────────────────┘  └────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                   SQLite + SQLAlchemy                  │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## 目录结构

```
202601_content_production_system_2/
├── docs/                    # 设计文档
│   ├── architecture.md      # 本文档
│   ├── agent_design.md      # Agent架构设计
│   ├── data_models.md       # 数据模型设计
│   └── api_design.md        # API接口设计
├── backend/                 # Python后端
│   ├── core/               # 核心业务逻辑
│   │   ├── models/         # SQLAlchemy模型
│   │   ├── modules/        # 业务模块
│   │   ├── tools/          # LangGraph工具
│   │   ├── prompt_engine.py
│   │   ├── ai_client.py
│   │   └── orchestrator.py # LangGraph Agent
│   ├── api/                # FastAPI路由
│   ├── tests/              # 测试
│   ├── main.py             # 入口
│   └── requirements.txt
├── frontend/               # Next.js前端
│   ├── app/               # App Router页面
│   ├── components/        # React组件
│   ├── lib/               # 工具函数
│   └── package.json
├── data/                   # SQLite数据库文件
├── .env.example           # 环境变量示例
└── README.md
```

## 数据流向

```
CreatorProfile（全局约束）
        ↓
Intent → ConsumerResearch → ContentCore → ContentExtension
                                 ↓              ↓
                            Simulator ←────────┘
                                 ↓
                              Report
```

## 核心设计原则

1. **Golden Context自动注入**: 每次LLM调用必须包含 创作者特质 + 核心意图 + 用户画像
2. **@引用机制**: 用户用@语法引用已有内容
3. **流式输出**: 所有LLM输出都通过SSE流式返回
4. **一致性保障**: 禁忌词检查 + 风格一致性检查 + 意图对齐检查

