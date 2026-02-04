# 架构调整方案与执行计划

> 创建时间: 2026-02-04
> 状态: 进行中

---

## 一、需求分析

### 1.1 核心需求
用户希望将当前固定的流程进度（意图分析→消费者调研→内涵设计→内涵生产→外延设计→外延生产→消费者模拟→评估）重构为**灵活、可配置、统一抽象**的结构。

### 1.2 关键点提取

| 需求项 | 当前状态 | 目标状态 |
|--------|----------|----------|
| 流程阶段 | 固定8个阶段 | 可添加/删除/排序 |
| 阶段模板 | 无 | 支持选择预设模板或自定义 |
| 字段层级 | 单层（除内涵设计有方案+字段两层） | 无限层级 |
| 依赖关系 | 通过 phase 隐式依赖 | 通过字段 ID 显式引用 |
| 特殊阶段 | 意图/调研/模拟/评估有特殊逻辑 | 保留特殊处理，但底层统一 |

---

## 二、统一抽象模型设计

### 2.1 核心概念：ContentBlock（内容块）

所有流程阶段、字段都统一为 **ContentBlock**：

```
ContentBlock {
  id: string                    // 唯一标识
  project_id: string            // 所属项目
  parent_id: string | null      // 父级内容块ID（null=顶级阶段）
  name: string                  // 名称
  block_type: string            // 类型：phase | field | proposal
  
  // 层级与排序
  depth: int                    // 层级深度（0=顶级阶段）
  order: int                    // 同级排序
  
  // 内容
  content: string               // 实际内容
  status: string                // pending | in_progress | completed
  
  // AI 配置
  ai_prompt: string             // 生成提示词
  constraints: JSON             // 约束配置（字数、格式等）
  
  // 依赖
  depends_on: string[]          // 依赖的其他 ContentBlock ID 列表
  
  // 特殊处理
  special_handler: string | null // 特殊处理器：intent | research | simulate | evaluate | null
  
  // 元数据
  need_review: bool             // 是否需要人工确认
  is_collapsed: bool            // UI 是否折叠
}
```

### 2.2 层级结构示例

```
项目
├── [阶段] 意图分析 (special_handler=intent)
│   └── [字段] 项目意图
├── [阶段] 消费者调研 (special_handler=research)
│   └── [字段] 消费者调研报告
├── [阶段] 内涵设计
│   ├── [方案] 方案一
│   │   ├── [字段] 核心论点
│   │   ├── [字段] 案例故事
│   │   └── [字段] 行动号召
│   └── [方案] 方案二
│       └── ...
├── [阶段] 内涵生产
│   ├── [字段] 核心论点（引用方案一.核心论点）
│   ├── [字段] 案例故事
│   └── [字段] 行动号召
├── [阶段] 自定义阶段（用户添加）
│   └── [字段] 自定义字段
└── [阶段] 评估 (special_handler=evaluate)
    └── [字段] 评估报告
```

### 2.3 阶段模板设计

```
PhaseTemplate {
  id: string
  name: string                  // "标准内容生产流程"
  description: string
  phases: [
    {
      name: "意图分析",
      special_handler: "intent",
      default_fields: [...],
      order: 1
    },
    ...
  ]
}
```

---

## 三、数据库变更方案

### 3.1 新增表：content_blocks

替代/合并现有的 `project_fields` 表：

```sql
CREATE TABLE content_blocks (
  id VARCHAR(36) PRIMARY KEY,
  project_id VARCHAR(36) NOT NULL,
  parent_id VARCHAR(36),              -- 父级块ID
  name VARCHAR(200) NOT NULL,
  block_type VARCHAR(50) NOT NULL,    -- phase | field | proposal
  depth INT DEFAULT 0,
  order_index INT DEFAULT 0,
  content TEXT DEFAULT '',
  status VARCHAR(20) DEFAULT 'pending',
  ai_prompt TEXT DEFAULT '',
  constraints JSON DEFAULT '{}',
  depends_on JSON DEFAULT '[]',
  special_handler VARCHAR(50),        -- intent | research | simulate | evaluate
  need_review BOOLEAN DEFAULT TRUE,
  is_collapsed BOOLEAN DEFAULT FALSE,
  created_at DATETIME,
  updated_at DATETIME,
  FOREIGN KEY (project_id) REFERENCES projects(id),
  FOREIGN KEY (parent_id) REFERENCES content_blocks(id)
);
```

### 3.2 新增表：phase_templates

```sql
CREATE TABLE phase_templates (
  id VARCHAR(36) PRIMARY KEY,
  name VARCHAR(200) NOT NULL,
  description TEXT,
  phases JSON NOT NULL,           -- 阶段定义数组
  is_default BOOLEAN DEFAULT FALSE,
  created_at DATETIME,
  updated_at DATETIME
);
```

### 3.3 项目表变更

从 `projects` 表移除固定的 `phase_order` 和 `phase_status`，改为通过 `content_blocks` 动态查询。

---

## 四、API 变更方案

### 4.1 新增 API

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/blocks/project/{project_id}` | 获取项目所有内容块（树形结构） |
| POST | `/api/blocks/` | 创建内容块 |
| PUT | `/api/blocks/{id}` | 更新内容块 |
| DELETE | `/api/blocks/{id}` | 删除内容块（级联删除子块） |
| POST | `/api/blocks/{id}/move` | 移动内容块（改变父级或排序） |
| POST | `/api/blocks/{id}/generate` | 生成内容块内容 |
| GET | `/api/phase-templates/` | 获取阶段模板列表 |
| POST | `/api/projects/{id}/apply-template` | 应用阶段模板到项目 |

### 4.2 兼容性处理

保留现有 `/api/fields/` API，内部转换为 content_blocks 操作，确保前端平滑过渡。

---

## 五、前端变更方案

### 5.1 进度面板重构

- 支持拖拽排序阶段
- 支持添加/删除阶段
- 支持展开/折叠层级
- 显示阶段模板选择器

### 5.2 内容面板重构

- 支持树形结构展示
- 支持拖拽移动字段到不同层级
- 支持添加子层级

---

## 六、执行计划 TODO List

### 阶段一：数据模型与后端基础（优先级最高）

- [x] **1.1** 创建 ContentBlock 模型 (`backend/core/models/content_block.py`) ✅
- [x] **1.2** 创建 PhaseTemplate 模型 (`backend/core/models/phase_template.py`) ✅
- [x] **1.3** 数据库迁移：创建 content_blocks 表 ✅
- [x] **1.4** 数据库迁移：创建 phase_templates 表 ✅
- [x] **1.5** 创建默认阶段模板数据 ✅

### 阶段二：后端 API 实现

- [x] **2.1** 实现 content_blocks CRUD API (`backend/api/blocks.py`) ✅
- [x] **2.2** 实现移动内容块 API ✅
- [x] **2.3** 实现内容块生成 API（复用现有生成逻辑）✅
- [x] **2.4** 实现阶段模板 API (`backend/api/phase_templates.py`) ✅
- [x] **2.5** 实现项目应用模板 API ✅
- [ ] **2.6** 兼容层：现有 `/api/fields/` 适配（可选，保持兼容）

### 阶段三：Orchestrator 适配

- [ ] **3.1** 修改 orchestrator 支持 content_blocks 结构（渐进式，保持兼容）
- [ ] **3.2** 修改特殊处理器（intent/research/simulate/evaluate）
- [ ] **3.3** 修改依赖解析逻辑（支持跨层级引用）

### 阶段四：前端重构

- [x] **4.1** 创建 ContentBlock 类型定义 ✅ (已存在于 api.ts)
- [x] **4.2** 创建 BlockTree 组件（树形展示）✅
- [ ] **4.3** 重构 ProgressPanel 支持动态阶段（可选，渐进式）
- [ ] **4.4** 重构 ContentPanel 支持层级结构（可选，渐进式）
- [x] **4.5** 实现拖拽排序功能 ✅ (已在 BlockTree 中实现)
- [x] **4.6** 实现阶段模板选择器 ✅

### 阶段五：数据迁移与测试

- [x] **5.1** 编写数据迁移脚本（project_fields → content_blocks）✅ (scripts/migrate_content_blocks.py)
- [ ] **5.2** 编写单元测试（待后续完善）
- [ ] **5.3** 端到端测试（待后续完善）
- [ ] **5.4** 性能测试（大量层级场景）（待后续完善）

---

## 九、已完成的核心改动汇总

### 后端
1. **新增模型**
   - `core/models/content_block.py` - 统一内容块模型，支持无限层级
   - `core/models/phase_template.py` - 阶段模板模型

2. **新增 API**
   - `api/blocks.py` - 内容块 CRUD、移动、生成 API
   - `api/phase_templates.py` - 模板管理 API

3. **数据库迁移**
   - `scripts/migrate_content_blocks.py` - 创建表、插入默认模板、迁移现有数据

4. **路由注册**
   - `main.py` - 注册新 API 路由

### 前端
1. **类型定义**
   - `lib/api.ts` - ContentBlock, BlockTree, PhaseTemplate 类型和 API

2. **新组件**
   - `components/block-tree.tsx` - 树形内容块展示，支持拖拽排序
   - `components/template-selector.tsx` - 阶段模板选择器

### 架构要点
- **统一抽象**: 所有阶段/字段/方案都是 ContentBlock
- **无限层级**: 通过 parent_id 实现树形结构
- **显式依赖**: depends_on 存储依赖块 ID 列表
- **特殊处理**: special_handler 区分意图/调研/模拟/评估
- **渐进兼容**: 保留现有 project_fields，新架构并行运行

---

## 七、执行日志

### 2026-02-04

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| - | 方案设计 | ✅ 完成 | 本文档 |
| - | 1.1 创建 ContentBlock 模型 | ✅ 完成 | 支持无限层级、依赖引用 |
| - | 1.2 创建 PhaseTemplate 模型 | ✅ 完成 | 包含默认流程模板 |
| - | 1.3-1.5 数据库迁移脚本 | ✅ 完成 | scripts/migrate_content_blocks.py |
| - | 2.1-2.5 实现后端 API | ✅ 完成 | blocks.py, phase_templates.py |
| - | 数据库迁移验证 | ✅ 完成 | 表创建成功 |
| - | 3.x Orchestrator 适配 | ⏸️ 暂缓 | 渐进式适配，保持兼容 |
| - | 4.1 ContentBlock 类型 | ✅ 完成 | api.ts |
| - | 4.2 BlockTree 组件 | ✅ 完成 | block-tree.tsx |
| - | 4.5 拖拽排序 | ✅ 完成 | 集成在 BlockTree |
| - | 4.6 模板选择器 | ✅ 完成 | template-selector.tsx |
| - | F1 视图切换 | ✅ 完成 | progress-panel.tsx |
| - | F2 BlockTree集成 | ✅ 完成 | progress-panel.tsx |
| - | F3 创建项目模板选择 | ✅ 完成 | create-project-modal.tsx |
| - | G1 虚拟树形结构 | ✅ 完成 | progress-panel.tsx |
| - | G2 选中块详情显示 | ✅ 完成 | content-panel.tsx |
| - | G3 双向同步 | ✅ 完成 | 通过 fields prop 自动同步 |

---

## 八、风险与注意事项

1. **数据迁移风险**：需要将现有 project_fields 数据迁移到 content_blocks，必须有回滚方案
2. **兼容性风险**：前端依赖现有 API 结构，需要保持兼容或同步更新
3. **性能风险**：无限层级可能导致查询性能问题，需要优化递归查询
4. **特殊处理器**：intent/research/simulate/evaluate 有特殊逻辑，需要仔细适配

---

## 十、用户视角评估标准（本次迭代）

### 10.1 合格的标准是什么？

从用户视角，看到的变化必须是**直观且可操作**的：

| 评估项 | 合格标准 | 验证方法 |
|--------|----------|----------|
| **1. 视图切换** | 左栏能在"传统视图"和"树形视图"间切换 | 点击切换按钮，两种视图都能正常显示 |
| **2. 树形展示** | 树形视图能正确显示阶段→字段的层级结构 | 看到缩进、展开/折叠、连接线 |
| **3. 添加阶段** | 能在树形视图底部添加新阶段 | 点击"添加阶段"，出现新节点 |
| **4. 添加字段** | 能在阶段下添加子字段 | 右键或菜单，选择添加字段 |
| **5. 拖拽排序** | 能拖拽调整阶段/字段顺序 | 拖动节点，顺序变化 |
| **6. 删除节点** | 能删除阶段或字段 | 菜单中点击删除，节点消失 |
| **7. 重命名** | 能重命名阶段或字段 | 双击或菜单，输入新名称 |
| **8. 状态显示** | 节点显示 pending/in_progress/completed 状态 | 看到不同颜色的状态指示器 |
| **9. 模板选择** | 新项目能选择流程模板 | 创建项目时看到模板列表 |

### 10.2 本次迭代 TODO

- [x] **F1** 在 ProgressPanel 添加视图切换（传统/树形）✅
- [x] **F2** 集成 BlockTree 到 ProgressPanel ✅
- [x] **F3** 将 TemplateSelector 集成到创建项目弹窗 ✅
- [x] **F4** workspace 页面连接 selectedBlock 状态 ✅
- [ ] **F5** 测试完整流程

### 10.3 第二轮迭代 TODO（解决已知限制）

**用户视角评估标准：**

| 评估项 | 合格标准 | 验证方法 |
|--------|----------|----------|
| **1. 树形视图有数据** | 传统项目切换到树形视图时，能看到现有阶段和字段 | 切换视图后，不再是空白 |
| **2. 自动同步** | 传统项目的 project_fields 自动映射为树形结构 | 无需手动操作，切换即可见 |
| **3. 选中显示详情** | 点击树形节点，ContentPanel 显示该节点内容 | 点击后中间面板更新 |
| **4. 编辑同步** | 在 ContentPanel 编辑内容，树形视图状态同步更新 | 编辑后状态和内容都更新 |

**实现 TODO：**

- [x] **G1** 修改 ProgressPanel：从 project_fields 动态构建虚拟树形结构 ✅
- [x] **G2** 修改 ContentPanel：接收 selectedBlock，显示对应内容 ✅
- [x] **G3** 实现双向同步：编辑 → 刷新树形视图 ✅ (通过 fields prop 自动同步)
- [x] **G4** 虚拟结构只读 + 迁移按钮 ✅
- [x] **G5** 后端迁移 API: `/api/blocks/project/{id}/migrate` ✅
- [ ] **G6** 完整测试

---

*本文档将随执行进度持续更新*
