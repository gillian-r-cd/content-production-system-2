<!--
功能: 日文版 locale 改造的零遗漏检查清单
主要用途: 作为各阶段执行后的复核基线，确保 AI 输入链路、资产、UI 与测试无遗漏
数据结构: 按阶段和资产类型组织的 Markdown checklist
-->

# JP Locale Zero-Omission Checklist

## Phase 0 Baseline
- [x] Cursor rules 已固化到 `.cursor/rules/*.mdc`
- [x] 已确认现有中文项目默认保持 `zh-CN`
- [x] 已记录所有 runtime prompt 入口
- [x] 已记录所有会进入项目实例化的模板/默认内容入口
- [x] 已记录所有需要双语并存的全局资产模型

## Data Model And API
- [x] `Project` 包含 `locale`
- [x] `SystemPrompt` 包含 `locale`
- [x] `FieldTemplate` 包含 `locale`
- [x] `CreatorProfile` 包含 `locale`
- [x] `Channel` 包含 `locale`
- [x] `Simulator` 包含 `locale`
- [x] `Grader` 包含 `locale`
- [x] `AgentMode` 包含 `locale`
- [x] 导入导出结构包含 `locale`
- [x] 复制/新版本/导入逻辑保留 `locale`

## Runtime Prompt Chain
- [x] `backend/core/prompt_engine.py`
- [x] `backend/core/block_generation_service.py`
- [x] `backend/core/agent_tools.py`
- [x] `backend/core/orchestrator.py`
- [x] `backend/api/blocks.py` AI 生成提示词入口
- [x] `backend/core/tools/outline_generator.py`
- [x] `backend/api/eval.py` prompt/persona 生成入口
- [x] `backend/core/tools/eval_engine.py`
- [x] 所有 fallback prompt 已 locale 化

## Seed Assets And Templates
- [x] `init_db.py` 的系统提示词双语化
- [x] `init_db.py` 的默认创作者特质双语化
- [x] `init_db.py` 的默认渠道双语化
- [x] `init_db.py` 的默认 Agent 模式双语化
- [x] Eval prompt presets 双语化
- [x] Grader presets 双语化
- [x] Simulator 默认模板双语化
- [x] Eval 模板字段双语化
- [x] 模板实例化按 locale 正确落块

## Frontend UI
- [x] 创建项目弹窗支持语言选择
- [x] 工作台主页面支持项目级 UI locale 切换
- [x] 设置页导航与各 section 文案支持 UI locale
- [x] 内容编辑关键面板支持 UI locale
- [x] Agent/Eval 关键面板支持 UI locale
- [x] 中文项目 UI 不回归

## Hardening Rules
- [x] 新增可本地化资产时必须同时声明 `stable_key` 与 `locale`
- [x] 新增进入 LLM 的控制层文本时必须通过 locale 驱动
- [x] 不允许通过散落硬编码字符串实现中日切换
- [x] `ja-JP` 资产修改后需通过静态扫描守卫
- [x] locale 改动后需补至少一条自动化回归测试

## Tests And Guards
- [x] 后端 locale 单元测试
- [x] 导入导出兼容测试
- [x] 模板应用语言正确性测试
- [x] 日文项目 prompt 输入不混中文测试
- [x] 前端组件测试覆盖语言选择与 UI 切换
- [x] E2E 覆盖中文项目无回归
- [x] E2E 覆盖日文项目完整主链
- [x] 静态扫描守卫测试可拦截中文残留
- [x] 生成日志 locale 自动化回归已补齐（替代人工抽样）
