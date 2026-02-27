# 本地部署与更新方案 - 修改文档

> 目标：让技术小白在终端中无痛完成首次部署、依赖安装、日常更新、启动项目，并保护本地数据。

## 问题分析

### 问题 1：首次 clone 后数据库为空，系统无法正常工作

**现状**：`main.py` 启动时调用 `init_db()` 只创建空表结构，但系统运行需要以下预置数据：
- CreatorProfile（创作者特质）
- SystemPrompt（系统提示词）
- AgentSettings（Agent 设置，含 tools 配置）
- Channel（渠道）
- Simulator（模拟器）
- Grader（评分器）
- AgentMode（Agent 模式）
- FieldTemplate（字段模板，含 Eval V2）

这些数据只有手动运行 `python -m scripts.init_db` 才会写入。

**根因**：`main.py` 的启动自愈逻辑只管 schema 不管 data。

**修复**：在 `main.py` 的 `_ensure_db_schema_on_startup()` 之后调用 `seed_default_data()`。
`seed_default_data()` 本身已是幂等的（每个表都先 `count() == 0` 再插入），不会破坏已有数据。

### 问题 2：sync.sh 缺少依赖安装

**现状**：`scripts/sync.sh` 只做 `git pull` + 清缓存，没有：
- `pip install -r requirements.txt`
- `npm install`
- 数据库 schema 同步

**根因**：脚本只考虑了代码同步，没考虑依赖和数据结构同步。

**修复**：在 `sync_code()` 中加入依赖安装步骤。数据库 schema 同步由 `main.py` 启动时自动完成，
无需脚本额外处理。

### 问题 3：没有首次部署的一键脚本

**现状**：首次 clone 需要手动：创建 venv -> 激活 -> pip install -> 复制 .env -> 编辑 .env ->
运行 init_db -> npm install -> 启动前后端。步骤过多易出错。

**修复**：创建 `scripts/setup.sh`，自动完成除"编辑 .env 填 API key"之外的所有步骤。
编辑 .env 必须由用户手动完成（涉及 API key 等敏感信息）。

### 问题 4：.gitignore 不完整，WAL 文件被追踪

**现状**：
- `.gitignore` 有 `*.db` 但没有 `*.db-shm`、`*.db-wal`、`*.db-journal`
- `backend/data/agent_checkpoints.db-shm` 和 `*.db-wal` 已被 git 追踪
- 这些 WAL 文件没有主 `.db` 文件就毫无意义，反而可能导致 SQLite 打开异常

**修复**：
1. `.gitignore` 追加 `*.db-shm`、`*.db-wal`、`*.db-journal`
2. `git rm --cached` 移除已追踪的 WAL 文件
3. 添加 `backend/data/.gitkeep` 确保目录在 clone 后存在

### 问题 5：Python 版本要求不准确

**现状**：README 和 requirements.txt 写 Python 3.14+，但实际 venv 是 3.9.6。
Python 3.14 还在 alpha/beta 阶段，对方无法安装。

**修复**：改为 Python 3.9+（与实际使用一致）。

---

## 修改清单

| # | 文件 | 操作 | 说明 |
|---|------|------|------|
| 1 | `.gitignore` | 修改 | 追加 `*.db-shm` / `*.db-wal` / `*.db-journal` |
| 2 | `backend/data/agent_checkpoints.db-shm` | git rm --cached | 从 git 移除追踪 |
| 3 | `backend/data/agent_checkpoints.db-wal` | git rm --cached | 从 git 移除追踪 |
| 4 | `backend/data/.gitkeep` | 新建 | 保证 clone 后目录存在 |
| 5 | `backend/main.py` | 修改 | 启动时自动 seed 空数据库 |
| 6 | `scripts/sync.sh` | 修改 | 加入 pip install + npm install |
| 7 | `scripts/setup.sh` | 新建 | 首次部署一键脚本 |
| 8 | `README.md` | 修改 | Python 版本改为 3.9+ |
| 9 | `backend/requirements.txt` | 修改 | Python 版本注释改为 3.9+ |

## 用户使用流程

### 首次部署

```bash
git clone https://github.com/gillian-r-cd/content-production-system-2.git
cd content-production-system-2
./scripts/setup.sh
# 按提示编辑 backend/.env 填入 API key
./scripts/sync.sh start
```

### 日常更新

```bash
./scripts/sync.sh start
```

此命令会依次：git pull -> 安装/更新依赖 -> 清缓存 -> 启动前后端。
数据库 schema 在后端启动时自动同步（`init_db()` + 兼容迁移），本地数据不受影响。

### 停止服务

```bash
./scripts/stop.sh
```

## 数据安全说明

- `.env` 文件已被 `.gitignore` 排除，不会上传
- `*.db` 文件已被 `.gitignore` 排除，本地数据库不会被 git 操作影响
- `git pull` 不会覆盖任何本地未追踪文件
- `seed_default_data()` 是幂等的：只在对应表为空时插入，已有数据不受影响
- `init_db()` 使用 `create_all()`：只创建不存在的表，不会 drop 已有表
- 列迁移使用 `ALTER TABLE ADD COLUMN`：只添加不存在的列，已有列不受影响
