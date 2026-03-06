# 版本管理闭环规划

## 一、问题诊断

### 1.1 当前系统中存在两套独立的版本机制

| 机制 | 数据模型 | 状态 |
|------|---------|------|
| **内容块级版本** (`ContentVersion`) | 每个 ContentBlock 修改前自动保存旧内容快照 | 功能完整，不需改动 |
| **项目级版本** (Project 深拷贝) | `projectAPI.createVersion()` 创建新 Project 行 + 复制所有 blocks | UI 层严重残缺 |

### 1.2 具体问题

1. **版本堆在项目列表中**: 项目级版本实现为独立 Project 行，`projectAPI.list()` 返回所有项目（含版本克隆），项目选择器扁平渲染，版本和原项目混在一起。

2. **左面板三个死按钮**: `progress-panel.tsx` 底部的「+ 新建版本」「查看历史版本」「导出内容」没有绑定任何事件处理器。

3. **后端版本查询按名称匹配**: `list_project_versions` 用 `Project.name == project.name` 查找版本族，同名项目会被误关联。

4. **闭环断裂**: 创建版本后无法浏览、无法切换回历史版本。

---

## 二、设计原则

1. **每个功能只在一个地方出现，不重复**
2. **不改数据模型，不涉及数据库迁移**
3. **最小改动量，逐步验证**

---

## 三、功能归属（唯一入口）

| 功能 | 唯一入口 | 说明 |
|------|---------|------|
| 导出项目 | 项目选择器下拉列表（每行操作按钮） | 已有，不动 |
| 查看/切换版本 | 项目选择器下拉列表（版本分组） | 需实现 |
| 创建新版本 | 项目选择器下拉列表（组内按钮） | 需实现 |
| 内容块版本历史 | 内容块工具栏「版本」按钮 | 已有，不动 |
| 上游变更提醒 | VersionWarningDialog 弹窗 | 已有，不动 |

---

## 四、具体改动

### 4.1 删除左面板「快捷操作」死按钮区域

**文件**: `frontend/components/progress-panel.tsx`

删除第 198-218 行的「分隔线 + 快捷操作」整个区域。左面板职责回归纯粹：项目信息 + 内容块树。

### 4.2 后端: 修复版本查询逻辑

**文件**: `backend/api/projects.py` 的 `list_project_versions` 函数

现状: 按 `Project.name` 匹配
改为: 沿 `parent_version_id` 链追溯版本族谱（向上找根 → 向下收集所有后代）

### 4.3 前端: 项目列表分组渲染

**文件**: `frontend/app/workspace/page.tsx` 项目选择器部分

改造项目选择器下拉列表:
- 将 `projects` 按版本族谱分组（通过后端 `parent_version_id` 或前端按 `name` 预分组）
- 每组默认折叠，只显示最新版本作为主行
- 点击展开箭头显示历史版本列表
- 点击某版本行 → `setCurrentProject(该版本)` 切换
- 组内底部放「+ 创建新版本」按钮

### 4.4 前端: 创建新版本交互

**文件**: `frontend/app/workspace/page.tsx`

在版本分组展开区域内:
- 「+ 创建新版本」按钮 → 弹出简单输入框让用户输入备注
- 调用 `projectAPI.createVersion(currentProjectId, note)`
- 创建完成后刷新项目列表

### 4.5 前端: 项目计数按族计算

**文件**: `frontend/app/workspace/page.tsx`

顶部操作栏的「N 个项目」改为按版本族计数，同一族只算一个。

---

## 五、Todolist（执行顺序）

- [ ] 1. 删除左面板「快捷操作」死按钮区域 (`progress-panel.tsx`)
- [ ] 2. 后端: 修复 `list_project_versions` 用 `parent_version_id` 链 (`projects.py`)
- [ ] 3. 前端: 项目列表按版本族分组渲染（折叠/展开） (`workspace/page.tsx`)
- [ ] 4. 前端: 组内「创建新版本」按钮 + 输入备注弹窗 (`workspace/page.tsx`)
- [ ] 5. 前端: 项目计数按族计算 (`workspace/page.tsx`)
- [ ] 6. 端到端验证完整闭环

---

## 六、不改动的部分

- 数据模型 (`Project`, `ContentVersion`, `ContentBlock`) — 不变
- 内容块级版本历史 (`version-history.tsx`, `version_service.py`) — 不动
- 上游变更弹窗 (`VersionWarningDialog`) — 不动
- 项目导出功能 — 保持在项目列表中，不重复
- 数据库 — 无迁移
