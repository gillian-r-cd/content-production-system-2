# backend/core/locale_text.py
# 功能: 统一管理运行时 locale 文案，避免 AI 控制层文本散落硬编码
# 主要函数: rt
# 数据结构: 按 locale 组织的运行时提示词模板字典

from __future__ import annotations

from core.localization import normalize_locale


RUNTIME_TEXTS = {
    "zh-CN": {
        "fallback.generate_content": "请生成内容。",
        "fallback.no_creator_profile": "（暂无创作者特质）",
        "fallback.no_dependencies": "（无依赖内容）",
        "fallback.no_channel": "（无渠道信息）",
        "golden_context.creator_profile_header": "# 创作者特质",
        "creator_profile.section_header": "## 创作者特质",
        "creator_profile.name_line": "名称: {name}",
        "creator_profile.trait.tone": "语调",
        "creator_profile.trait.vocabulary": "词汇",
        "creator_profile.trait.personality": "人物设定",
        "creator_profile.trait.style": "风格",
        "creator_profile.trait.taboos": "禁忌",
        "creator_profile.trait.audience": "受众偏好",
        "creator_profile.trait.structure": "结构偏好",
        "markdown.instructions": """# 输出格式（必须遵守）
使用 Markdown 格式输出。
- 标题使用 # ## ### 格式
- 列表使用 - 或 1. 格式
- 重点内容使用 **粗体** 或 *斜体*
- 表格必须包含表头分隔行（如 | --- | --- |），且每行列数与表头一致
- 若一个单元格需要多条内容，用 <br> 换行，不要增加 | 列分隔符""",
        "block.pre_answers_header": "\n---\n# 用户补充信息（生成前提问的回答）\n{answers}",
        "block.task_header": "# 当前任务",
        "block.reference_header": "# 参考内容",
        "block.markdown_tail": "\n\n---\n{instructions}",
        "block.generate.human": "请生成「{name}」的内容。",
        "block.dependencies_missing_content": "以下依赖内容尚未完成: {missing_labels}",
        "pre_questions.missing_required": "以下必答生成前提问尚未回答: {missing_labels}",
        "prompt_context.channel_header": "# 目标渠道",
        "prompt_context.field_target_header": "# 当前要生成的字段",
        "prompt_context.field_name_line": "字段名称：{name}",
        "prompt_context.field_requirement_header": "# 具体生成要求",
        "prompt_context.field_pre_answers_header": "# 用户补充信息\n{answers}",
        "phase_prompt.intent.questioning": """你是一个专业的内容策略顾问。你的任务是通过 3 个问题帮助用户澄清内容生产的意图。

问题顺序（根据对话历史判断当前应该问哪个）：

1. 【先了解项目是什么】如果用户还没说清楚想做什么内容，先问：
   "你这次想做什么内容？请简单描述一下（比如：一篇文章、一个视频脚本、一份产品介绍...）"

2. 【再问目标受众】了解内容是什么后，问：
   "这个内容主要写给谁看？请用「岗位/角色 + 所在行业 + 当前面临的 1-2 个痛点」来描述，比如：'中大型制造企业的 IT 负责人，正在推进数字化转型但缺乏内部数据基础'"

3. 【最后问期望效果】了解受众后，问：
   "看完这个内容后，你最希望读者立刻采取的一个具体行动是什么？"

规则：
- 根据对话历史判断用户已经回答了哪些问题，不要重复问
- 每次只问 1 个问题
- 问题要简洁明了""",
        "phase_prompt.intent.producing": """你是一个专业的内容策略顾问。根据用户的回答，提取 3 个核心字段。

请严格按以下 JSON 格式输出（不要添加任何其他内容）：

```json
{
  "做什么": "用一句话描述这个内容的主题和形式，例如：一份面向一线经理的 AI 对练 chatbot 设计方案",
  "给谁看": "目标受众的具体描述，包含角色、行业、痛点，例如：互联网/制造业的一线经理，面临绩效面谈、冲突处理等管理场景缺乏练习机会",
  "期望行动": "读者看完后最希望采取的具体行动，例如：主动尝试使用 AI 对练工具进行一次模拟管理对话"
}
```

规则：
- 每个字段的内容要简洁有力，1-2 句话
- 直接从用户回答中提炼，不要自己发挥
- 只输出 JSON，不要其他解释

请基于用户的所有回答，生成完整、具体、可操作的意图分析报告。""",
        "phase_prompt.research": """【创作者特质】
{creator_profile}

---

你是一个资深的用户研究专家。基于以下参考内容，进行消费者调研。

【参考内容】
{dependencies}

你需要输出：
1. 总体用户画像（年龄、职业、特征）
2. 核心痛点（3-5 个）
3. 价值主张（3-5 个）
4. 典型用户小传（3 个，包含完整的故事背景）

输出格式要求结构化、具体、可操作。""",
        "phase_prompt.design_inner": """【创作者特质】
{creator_profile}

---

你是一个资深的内容架构师。基于以下参考内容，设计 3 个不同的内容生产方案供用户选择。

【参考内容】
{dependencies}

你必须输出严格的 JSON 格式（不要添加任何其他内容），包含 3 个方案：

```json
{{
  "proposals": [
    {{
      "id": "proposal_1",
      "name": "方案名称（简洁有力）",
      "description": "方案核心思路描述（2-3 句话）",
      "fields": [
        {{
          "id": "field_1",
          "name": "字段名称",
          "field_type": "richtext",
          "ai_prompt": "生成这个字段时的 AI 提示词",
          "depends_on": [],
          "order": 1,
          "need_review": true
        }},
        {{
          "id": "field_2",
          "name": "第二个字段",
          "field_type": "richtext",
          "ai_prompt": "生成提示词",
          "depends_on": ["field_1"],
          "order": 2,
          "need_review": false
        }}
      ]
    }},
    {{ ... }},
    {{ ... }}
  ]
}}
```

要求：
1. 3 个方案要有明显差异（如：模块化 vs 线性 vs 场景驱动）
2. 每个方案 5-10 个字段
3. 字段依赖关系要合理（depends_on 填写依赖的字段 id）
4. need_review 默认为 true（需人工确认后才生成），仅对确定可自动执行的字段设为 false
5. 紧扣用户痛点和项目意图""",
        "phase_prompt.produce_inner": """【创作者特质】
{creator_profile}

---

你是一个专业的内容创作者。根据以下参考内容，生产具体的内容。

【参考内容】
{dependencies}

要求：
1. 严格遵循创作者特质和风格
2. 紧扣项目意图
3. 回应用户痛点
4. 输出高质量、可直接使用的内容""",
        "phase_prompt.design_outer": """【创作者特质】
{creator_profile}

---

你是一个资深的营销策略专家。基于以下已生产的内涵内容，设计外延传播方案。

【参考内容】
{dependencies}

你需要输出：
1. 推荐的传播渠道及理由
2. 各渠道的内容策略
3. 核心传播信息提炼
4. 关键注意事项""",
        "phase_prompt.produce_outer": """【创作者特质】
{creator_profile}

---

你是一个全渠道内容运营专家。根据以下外延设计方案，为指定渠道生产内容。

【参考内容】
{dependencies}

【目标渠道】
{channel}

要求：
1. 严格遵循渠道规范和限制
2. 保持与内涵内容的一致性
3. 适配渠道用户的阅读习惯
4. 输出可直接发布的内容""",
        "phase_prompt.evaluate": """【创作者特质】
{creator_profile}

---

你是一个资深的内容评审专家。请对以下内容进行全面评估。

【参考内容】
{dependencies}

评估维度：
1. 意图对齐度
2. 用户匹配度
3. 内容质量
4. 模拟反馈综合

输出：
1. 各维度评分和评语
2. 具体的修改建议（可操作）
3. 总体评价""",
        "agent.reference_block_header": "### 参考内容块「{label}」",
        "agent.reference_section_header": "## 参考内容",
        "agent.reference_context.target": "[引用目标] {label}",
        "agent.reference_context.empty_content": "（此内容块尚无正文内容）",
        "agent.reference_context.ai_prompt": "[该内容块的 AI 提示词配置]",
        "agent.reference_context.status": "[状态: {status}]",
        "agent.references.user_header": "以下是用户引用的内容块：",
        "agent.references.selection_header": "[引用上下文]",
        "agent.references.block_item": "【{name}】",
        "agent.references.selected_text": "用户在内容块「{block_name}」中选中了以下内容：",
        "agent.references.full_block": "该内容块完整内容：",
        "agent.references.duplicate_name": "内容块名称「{name}」命中多个结果，请改用 id:块ID 指定。候选：{candidates}",
        "agent.error.timeout_message": "⚠️ 处理超时，请稍后重试。",
        "agent.error.timeout_detail": "Agent 处理超时",
        "agent.error.failed_prefix": "⚠️ 处理失败: {message}",
        "agent.mode.missing": "当前项目尚未配置 Agent 角色，请先在右侧面板创建角色或导入模板。",
        "project.duplicate.name": "{name} (副本)",
        "project.duplicate.version_note": "从项目复制",
        "project.import.default_creator_name": "导入的创作者",
        "project.import.default_project_name": "导入的项目",
        "project.import.default_version_note": "从导出文件导入",
        "project.import.default_eval_run_name": "评估运行",
        "project.import.default_mode_display_name": "导入角色",
        "project.import.success": "项目「{name}」导入成功",
        "project.import.failed": "导入失败: {message}",
        "phase_template.duplicate.name": "{name} (副本)",
        "phase_template.apply.success": "已应用模板「{name}」",
        "agent.conversation.default_title": "新会话",
        "agent.tool.seed_message": "调用工具: {tool_name}",
        "agent.tool.unknown": "未知工具: {tool_name}。可用工具: {available}",
        "agent.tool.failed": "工具执行失败: {message}",
        "inline_edit.empty_text": "未选中任何文本",
        "inline_edit.empty_instruction": "自定义修改指令不能为空",
        "inline_edit.unsupported_operation": "不支持的操作: {operation}。可选: rewrite, expand, condense, custom",
        "inline_edit.operation.rewrite": "改写以下文本，使其更清晰、更专业，保持原意不变。",
        "inline_edit.operation.expand": "扩展以下文本，增加更多细节和论证，使其更加丰富和有说服力。",
        "inline_edit.operation.condense": "精简以下文本，保留核心信息，去除冗余，使其更加简洁有力。",
        "inline_edit.creator_context": "\n\n创作者风格参考：\n{creator_profile}",
        "inline_edit.system": """你是一位专业的内容编辑。请执行以下改写任务：
{instruction}

规则：
- 只输出修改后的文本，不要添加任何解释、标注或注释
- 保持原文的格式（Markdown 标题级别、列表样式等）
- 如果提供了上下文，参考上下文保持风格和术语一致性
- 不要输出引号包裹结果{creator_context}""",
        "inline_edit.user_with_context": "上下文（仅供参考，不要修改）：\n{context}\n\n---\n需要修改的文本：\n{text}",
        "inline_edit.user_without_context": "需要修改的文本：\n{text}",
        "inline_edit.failed": "AI 处理失败: {message}",
        "blocks.generate_prompt.user": "请为以下字段生成 AI 提示词：\n\n{field_line}字段目的: {purpose}{project_line}",
        "blocks.generate_prompt.fallback_system": """你是一个专业的提示词工程师。用户会告诉你某个字段的目的和需求，你需要为该字段生成一段高质量的 AI 提示词。

生成的提示词应该：
1. 明确指出 AI 的角色定位
2. 清晰描述要生成的内容是什么
3. 给出具体的输出要求（格式、结构、风格等）
4. 如果有依赖上下文，提醒 AI 参考这些信息
5. 包含质量约束

直接输出提示词内容，不需要任何解释或前缀。""",
        "agent.rewrite.system": """你是一个专业的内容修改助手。请根据指令修改以下内容块，保持原有风格和结构。

## 当前内容块：{target_label}
{current_content}
{reference_section}

## 修改要求
{instruction}

请直接输出修改后的完整内容，不要添加任何解释或前缀。""",
        "agent.rewrite.human": "请按要求修改「{target_label}」的内容。",
        "agent.generate.intro": "你是一个专业的内容创作助手。请为「{target_label}」生成高质量的内容。",
        "agent.generate.creator": "## 创作者信息\n{creator_ctx}",
        "agent.generate.requirement": "## 内容块要求\n{ai_prompt}",
        "agent.generate.dependencies": "## 依赖内容（作为参考）{deps_ctx}",
        "agent.generate.instruction": "## 额外指令\n{instruction}",
        "agent.generate.output_only": "请直接输出内容，不要添加前缀或解释。",
        "agent.generate.human": "请生成「{target_label}」的内容。",
        "agent.query.system": "你是内容分析助手。以下是内容块「{target_label}」的内容：\n\n{content}",
        "orchestrator.default_identity": "你是一个智能内容生产 Agent，帮助创作者完成从意图分析到内容发布的全流程。",
        "orchestrator.time_context": "当前系统时间: {timestamp}\n今天是: {weekday}\n时间解释规则: 用户提到“以来”“最近”“截至今天”时，以上述系统时间为准。",
        "orchestrator.intent_guide": """
## 🎯 意图分析流程（当前组 = intent）
你当前正在帮助创作者明确内容目标。请通过 3 轮对话收集以下信息：

1. **做什么**（主题和目的）— 问法举例：「你这次想做什么内容？请简单描述主题或方向。」
2. **给谁看**（目标受众）— 根据上一个回答个性化提问
3. **期望行动**（看完后希望受众做什么）— 根据之前的回答个性化提问

### 流程规则
- 每次只问一个问题，用编号标记（如【问题 1/3】）
- 用户回答后，先简要确认你的理解，再追问下一个
- 3 个问题都回答后：
  1. 输出结构化的意图分析摘要
  2. 调用 update_field(field_name="意图分析", content=摘要内容) 保存
  3. 告诉用户「✅ 已生成意图分析，请在工作台查看。输入"继续"进入下一组」
- **如果用户在此阶段问其他问题（如"你能做什么"），正常回答，不影响问答流程**
- **如果用户说"继续"/"下一步"且意图分析已保存，提示其在工作台选择下一步要处理的节点**
""",
        "outline.system": """你是一个专业的内容架构师。请根据项目信息生成结构化的内容大纲。

## 项目信息
- 内容类型: {content_type}
- 创作者特质: {creator_profile}
- 项目意图: {intent}
- 目标用户: {research}

## 大纲要求
{structure_hint}

典型板块参考（可调整）: {typical_sections}

## 输出格式
请以 JSON 格式输出大纲，结构如下：
```json
{{
    "title": "大纲标题",
    "summary": "大纲概述（1-2句话）",
    "nodes": [
        {{
            "name": "板块名称",
            "description": "板块描述",
            "ai_prompt": "生成该板块内容时的AI提示词",
            "depends_on": ["依赖的其他板块名称"],
            "children": [
                {{
                    "name": "子板块名称",
                    "description": "子板块描述",
                    "ai_prompt": "AI提示词",
                    "depends_on": []
                }}
            ]
        }}
    ]
}}
```

规则：
1. 大纲应该逻辑清晰、层次分明
2. ai_prompt 要具体明确，能指导AI生成内容
3. depends_on 列出该板块需要依赖的前置板块
4. children 用于嵌套子板块（如章节下的小节）
5. 根据项目特点决定是否需要嵌套

只输出JSON，不要其他解释。""",
        "outline.human": "请生成内容大纲",
        "eval.persona.system": "你是一位人物画像设计专家，请严格输出 JSON，不要输出额外文字。",
        "eval.persona.user": """请为以下项目生成一个新的用户画像（避免与已有画像重复）：

【项目名称】
{project_name}

【项目意图】
{project_intent}

【已有画像名称（避免重复）】
{names_text}

输出 JSON:
{{"name":"画像名称","prompt":"完整画像提示词（包含身份、背景、核心需求、顾虑、决策标准）"}}""",
        "eval.persona.fallback_name": "新画像",
        "eval.persona.fallback_prompt": "你是{name}，请基于项目目标给出真实消费者视角反馈。",
        "eval.persona.fallback_default": "你是一个潜在消费者，关注内容是否真正解决你的核心问题、成本是否合理、执行是否可行。",
        "eval.prompt.system": "你是一位提示词工程专家。请严格输出 JSON，不要输出额外文字。",
        "eval.prompt.user": """请为以下评估场景生成提示词：

【提示词类型】{prompt_type_name}
【评估形态】{form_type_name}
【角色/场景描述】{description}
【项目背景】{project_context}
【必须包含占位符】{required_placeholders}

要求：
1) 角色定义清晰；
2) 行为要求具体；
3) 如果是评分场景，请包含评分锚点；
4) 包含结构化 JSON 输出格式说明；
5) 保留必须占位符。

输出 JSON:
{{"generated_prompt":"完整提示词"}}""",
        "eval.prompt.fallback": "你是评估专家。请基于提供内容执行评估，并严格输出 JSON 结果。",
        "eval_engine.review_default": "请评估以下内容。",
        "eval.prompt.focus_header": "【本次焦点】\n{probe}",
        "eval.experience.no_blocks": "没有可探索的内容块",
        "eval.experience.default_persona_prompt": "你是一个真实消费者。",
        "eval.experience.block_fallback_title": "内容块{index}",
        "eval.experience.probe_section": "【你的核心关切】\n{probe}",
        "eval.experience.memory_none": "（无）",
        "eval.experience.no_doubt": "无疑虑",
        "eval.experience.memory_line": "{block_title}:{doubt}({score}分)",
        "eval.experience.stage_plan": "阶段1-探索规划",
        "eval.experience.stage_per_block": "阶段2-逐块探索",
        "eval.experience.stage_summary": "阶段3-总体总结",
        "eval.experience.plan.system": "你是一位真实的消费者，请严格按 JSON 输出，不要输出额外文字。",
        "eval.experience.plan.user": """【你的身份】
{persona_prompt}

{probe_section}

你面前有以下内容块：
{block_list}

请严格输出 JSON（不允许 Markdown/解释）:
{{"plan":[{{"block_id":"id","block_title":"标题","reason":"为什么先看","expectation":"期望找到什么"}}],"overall_goal":"1句话目标"}}

强约束：
1) plan 必须包含 3-5 个步骤；若内容块少于3个，则全部列出且不得为空。
2) 每个步骤都必须引用有效 block_id（来自上方列表），不得杜撰。
3) 如果无法判断优先级，也必须给出默认顺序，不能省略步骤。""",
        "eval.experience.per_block.system": "你是一位真实消费者，请按要求输出 JSON。",
        "eval.experience.per_block.user": """【你的身份】
{persona_prompt}

{probe_section}

【之前的阅读记忆】
{exploration_memory}

【当前内容块】
标题：{block_title}
内容：
{block_content}

请严格输出 JSON（不允许 Markdown/解释）:
{{"concern_match":"...","discovery":"...","doubt":"...","missing":"...","feeling":"作为{persona_name}的感受","score":1-10}}

强约束：
1) score 必须是 1-10 的整数；不确定时给保守分并在 doubt 说明原因。
2) missing 必须是可执行的补充项（具体到信息/案例/步骤），禁止抽象空话。
3) discovery / doubt 需要基于当前内容块证据，不得脱离文本臆测。""",
        "eval.experience.summary.system": "你是一位真实消费者，请按 JSON 输出总结。",
        "eval.experience.summary.user": """【你的身份】
{persona_prompt}

{probe_section}

以下是你逐块探索结果：
{all_block_results}

请严格输出 JSON（不允许 Markdown/解释）:
{{"overall_impression":"...","concerns_addressed":[],"concerns_unaddressed":[],"would_recommend":true,"summary":"作为{persona_name}的总体评价"}}

强约束：
1) concerns_addressed / concerns_unaddressed 的每一项，都必须能在逐块结果中找到依据。
2) summary 必须明确包含“是否推荐 + 推荐条件/不推荐原因”，不得只写笼统结论。
3) 如果信息不足，必须在 concerns_unaddressed 中明确指出缺口。""",
    },
    "ja-JP": {
        "fallback.generate_content": "内容を生成してください。",
        "fallback.no_creator_profile": "（クリエイタープロファイル未設定）",
        "fallback.no_dependencies": "（参照コンテンツなし）",
        "fallback.no_channel": "（対象チャネル情報なし）",
        "golden_context.creator_profile_header": "# クリエイタープロファイル",
        "creator_profile.section_header": "## クリエイタープロファイル",
        "creator_profile.name_line": "名前: {name}",
        "creator_profile.trait.tone": "トーン",
        "creator_profile.trait.vocabulary": "語彙",
        "creator_profile.trait.personality": "人物像",
        "creator_profile.trait.style": "スタイル",
        "creator_profile.trait.taboos": "避けること",
        "creator_profile.trait.audience": "想定読者",
        "creator_profile.trait.structure": "構成方針",
        "markdown.instructions": """# 出力形式（必須）
Markdown 形式で出力してください。
- 見出しは # ## ### を使う
- リストは - または 1. を使う
- 強調は **太字** または *斜体* を使う
- 表はヘッダー区切り行（例: | --- | --- |）を含め、各行の列数を揃える
- 1 つのセルに複数項目を入れる場合は <br> で改行し、| を増やさない""",
        "block.pre_answers_header": "\n---\n# ユーザー補足情報（事前質問への回答）\n{answers}",
        "block.task_header": "# 現在のタスク",
        "block.reference_header": "# 参考情報",
        "block.markdown_tail": "\n\n---\n{instructions}",
        "block.generate.human": "「{name}」の内容を生成してください。",
        "block.dependencies_missing_content": "以下の依存コンテンツが未完了です: {missing_labels}",
        "pre_questions.missing_required": "未回答の必須事前質問があります: {missing_labels}",
        "prompt_context.channel_header": "# 対象チャネル",
        "prompt_context.field_target_header": "# これから生成する内容ブロック",
        "prompt_context.field_name_line": "内容ブロック名: {name}",
        "prompt_context.field_requirement_header": "# 具体的な生成要件",
        "prompt_context.field_pre_answers_header": "# ユーザー補足情報\n{answers}",
        "phase_prompt.intent.questioning": """あなたはコンテンツ戦略コンサルタントです。3 つの質問を通じて、ユーザーのコンテンツ制作意図を明確にしてください。

質問順序（対話履歴を見て次に聞くべきものを判断してください）：

1. 【まず何を作るか】まだ作りたい内容が明確でない場合は、次のように尋ねてください。
   「今回はどのようなコンテンツを作りたいですか？簡単に教えてください（例: 記事、動画台本、製品紹介資料など）」

2. 【次に誰向けか】内容が分かったら、次のように尋ねてください。
   「そのコンテンツは主に誰に届けたいですか？『職種 / 役割 + 業界 + 現在の 1〜2 個の課題』の形で教えてください。」

3. 【最後に期待する行動】読者像が分かったら、次のように尋ねてください。
   「そのコンテンツを読んだあと、相手にまず取ってほしい具体的な行動は何ですか？」

ルール:
- すでに回答済みの質問は繰り返さない
- 1 回につき質問は 1 つだけ
- 質問は簡潔で、実務判断に使える粒度にする""",
        "phase_prompt.intent.producing": """あなたはコンテンツ戦略コンサルタントです。ユーザーの回答から 3 つの核心フィールドを抽出してください。

必ず次の JSON 形式のみを出力してください（余計な説明は禁止）：

```json
{
  "何を作るか": "このコンテンツのテーマと形式を 1 文でまとめる。例: 現場マネージャー向けの AI ロールプレイ chatbot 設計案",
  "誰に向けるか": "対象読者を役割・業界・課題まで具体化して書く。例: 製造業 / IT 部門の責任者で、DX を進めたいが社内データ基盤が弱い人",
  "期待する行動": "読後に最も取ってほしい具体行動を書く。例: AI ロールプレイツールを使って 1 回試してみる"
}
```

ルール:
- 各項目は簡潔かつ具体的に、1〜2 文でまとめる
- ユーザー回答から抽出し、勝手に話を膨らませない
- JSON 以外は出力しない

ユーザーの全回答を踏まえて、完全で具体的かつ実行可能な意図整理結果を作成してください。""",
        "phase_prompt.research": """【クリエイタープロファイル】
{creator_profile}

---

あなたは上級ユーザーリサーチャーです。以下の参考情報を基に、消費者調査を実施してください。

【参考情報】
{dependencies}

出力内容:
1. 全体ユーザー像
2. 主要課題（3-5 個）
3. 価値訴求（3-5 個）
4. 代表的ペルソナ小伝（3 名）

構造化され、具体的で実務に使える形で出力してください。""",
        "phase_prompt.design_inner": """【クリエイタープロファイル】
{creator_profile}

---

あなたはコンテンツ設計の専門家です。以下の参考情報を基に、異なる方向性を持つ 3 つの制作案を設計してください。

【参考情報】
{dependencies}

必ず JSON のみを出力し、案ごとの名称、説明、フィールド、依存関係、レビュー要否を含めてください。""",
        "phase_prompt.produce_inner": """【クリエイタープロファイル】
{creator_profile}

---

あなたはコンテンツ制作者です。以下の参考情報を基に、実際に利用可能な高品質コンテンツを作成してください。

【参考情報】
{dependencies}

要件:
1. クリエイタープロファイルのトーンとスタイルを守る
2. プロジェクト意図に沿う
3. ユーザー課題に応える
4. そのまま使える品質で出力する""",
        "phase_prompt.design_outer": """【クリエイタープロファイル】
{creator_profile}

---

あなたはマーケティング戦略の専門家です。制作済みの中核コンテンツを基に、外部展開プランを設計してください。

【参考情報】
{dependencies}

出力内容:
1. 推奨チャネルとその理由
2. 各チャネル向けの内容戦略
3. 主要メッセージの整理
4. 実行時の注意点""",
        "phase_prompt.produce_outer": """【クリエイタープロファイル】
{creator_profile}

---

あなたはマルチチャネル運用の専門家です。以下の参考情報を基に、指定チャネル向けの公開可能な内容を制作してください。

【参考情報】
{dependencies}

【対象チャネル】
{channel}

要件:
1. チャネル固有の制約と文法を守る
2. 中核コンテンツとの一貫性を保つ
3. チャネル利用者の読解習慣に合わせる
4. そのまま公開できる完成度で出力する""",
        "phase_prompt.evaluate": """【クリエイタープロファイル】
{creator_profile}

---

あなたはコンテンツ評価の専門家です。以下の内容を総合的に評価し、点数、講評、改善提案を提示してください。

【参考情報】
{dependencies}

評価観点:
1. 意図との整合性
2. 対象読者との適合性
3. 内容品質
4. 模擬フィードバックの総合評価

出力内容:
1. 各観点の点数と講評
2. 実行可能な改善提案
3. 総合評価""",
        "agent.reference_block_header": "### 参照コンテンツブロック「{label}」",
        "agent.reference_section_header": "## 参考情報",
        "agent.reference_context.target": "[参照対象] {label}",
        "agent.reference_context.empty_content": "（この内容ブロックにはまだ本文がありません）",
        "agent.reference_context.ai_prompt": "[この内容ブロックの AI プロンプト設定]",
        "agent.reference_context.status": "[ステータス: {status}]",
        "agent.references.user_header": "以下はユーザーが参照した内容ブロックです:",
        "agent.references.selection_header": "[参照コンテキスト]",
        "agent.references.block_item": "【{name}】",
        "agent.references.selected_text": "ユーザーは内容ブロック「{block_name}」で次のテキストを選択しています:",
        "agent.references.full_block": "この内容ブロックの全文:",
        "agent.references.duplicate_name": "内容ブロック名「{name}」に複数候補があります。id:ブロックID で指定してください。候補: {candidates}",
        "agent.error.timeout_message": "⚠️ 処理がタイムアウトしました。しばらくしてから再試行してください。",
        "agent.error.timeout_detail": "Agent の処理がタイムアウトしました",
        "agent.error.failed_prefix": "⚠️ 処理に失敗しました: {message}",
        "agent.mode.missing": "このプロジェクトにはまだ Agent ロールがありません。右側パネルでロールを作成するか、テンプレートを取り込んでください。",
        "project.duplicate.name": "{name}（コピー）",
        "project.duplicate.version_note": "プロジェクトを複製して作成",
        "project.import.default_creator_name": "インポートしたクリエイター",
        "project.import.default_project_name": "インポートしたプロジェクト",
        "project.import.default_version_note": "エクスポートファイルからインポート",
        "project.import.default_eval_run_name": "評価実行",
        "project.import.default_mode_display_name": "インポートしたロール",
        "project.import.success": "プロジェクト「{name}」をインポートしました",
        "project.import.failed": "インポートに失敗しました: {message}",
        "phase_template.duplicate.name": "{name}（コピー）",
        "phase_template.apply.success": "テンプレート「{name}」を適用しました",
        "agent.conversation.default_title": "新しい会話",
        "agent.tool.seed_message": "ツール呼び出し: {tool_name}",
        "agent.tool.unknown": "未知のツールです: {tool_name}。利用可能: {available}",
        "agent.tool.failed": "ツール実行に失敗しました: {message}",
        "inline_edit.empty_text": "編集対象のテキストが選択されていません",
        "inline_edit.empty_instruction": "カスタム編集指示は必須です",
        "inline_edit.unsupported_operation": "未対応の操作です: {operation}。利用可能: rewrite, expand, condense, custom",
        "inline_edit.operation.rewrite": "以下のテキストを、意味を変えずに、より明確でプロフェッショナルな表現に書き換えてください。",
        "inline_edit.operation.expand": "以下のテキストを、詳細や根拠を補って、より豊かで説得力のある内容に広げてください。",
        "inline_edit.operation.condense": "以下のテキストを、要点を保ったまま冗長さを減らし、より簡潔で力強い表現に整えてください。",
        "inline_edit.creator_context": "\n\nクリエイター特性の参考:\n{creator_profile}",
        "inline_edit.system": """あなたはプロのコンテンツ編集者です。次の編集タスクを実行してください。
{instruction}

ルール:
- 修正後のテキストのみを出力し、説明・注釈・マークアップは付けない
- 元の書式（Markdown 見出し、リスト形式など）を維持する
- 文脈がある場合は、それを参照して語彙・トーン・表現を合わせる
- 結果を引用符で囲まない{creator_context}""",
        "inline_edit.user_with_context": "文脈（参照のみ。ここは書き換えないでください）:\n{context}\n\n---\n編集対象のテキスト:\n{text}",
        "inline_edit.user_without_context": "編集対象のテキスト:\n{text}",
        "inline_edit.failed": "AI 編集に失敗しました: {message}",
        "blocks.generate_prompt.user": "以下の項目に対する AI プロンプトを作成してください。\n\n{field_line}項目の目的: {purpose}{project_line}",
        "blocks.generate_prompt.fallback_system": """あなたはプロンプト設計の専門家です。ユーザーが伝える項目の目的と要件を基に、そのまま AI に渡せる高品質なプロンプトを作成してください。

プロンプトには次の要素を含めてください。
1. AI の役割定義
2. 生成すべき内容の明確な説明
3. 出力形式・構成・文体などの具体要件
4. 依存コンテキストがある場合は参照指示
5. 品質制約と注意点

出力は完成したプロンプト本文のみとし、前置きや解説は不要です。""",
        "agent.rewrite.system": """あなたはコンテンツ改稿の専門アシスタントです。指示に従って、対象コンテンツブロックを元の文体と構造を保ちながら修正してください。

## 対象コンテンツブロック: {target_label}
{current_content}
{reference_section}

## 修正要件
{instruction}

修正後の完全版のみを出力し、解説や前置きは付けないでください。""",
        "agent.rewrite.human": "「{target_label}」の内容を指示どおり修正してください。",
        "agent.generate.intro": "あなたはコンテンツ制作アシスタントです。 「{target_label}」に対して高品質な内容を生成してください。",
        "agent.generate.creator": "## クリエイター情報\n{creator_ctx}",
        "agent.generate.requirement": "## コンテンツブロック要件\n{ai_prompt}",
        "agent.generate.dependencies": "## 依存コンテンツ（参考）{deps_ctx}",
        "agent.generate.instruction": "## 追加指示\n{instruction}",
        "agent.generate.output_only": "本文のみを出力し、前置きや説明は不要です。",
        "agent.generate.human": "「{target_label}」の内容を生成してください。",
        "agent.query.system": "あなたはコンテンツ分析アシスタントです。以下はコンテンツブロック「{target_label}」の内容です。\n\n{content}",
        "orchestrator.default_identity": "あなたはインテリジェントなコンテンツ制作 Agent です。意図整理から公開用コンテンツ作成まで、制作プロセス全体を支援します。",
        "orchestrator.time_context": "現在のシステム時刻: {timestamp}\n本日の曜日: {weekday}\n時間解釈ルール: ユーザーが「最近」「今日時点で」「以降」などと述べた場合は、このシステム時刻を基準に解釈してください。",
        "orchestrator.intent_guide": """
## 🎯 意図整理フロー（現在のグループ = intent）
現在は、クリエイターのコンテンツ目的を明確化する段階です。3 回の対話で次の情報を収集してください。

1. **何を作るか**（テーマと目的）
2. **誰に向けるか**（対象読者・顧客）
3. **期待する行動**（読後に取ってほしい具体的行動）

### 進行ルール
- 1 回につき質問は 1 つだけ行う
- ユーザーの回答後、理解を短く確認してから次の質問へ進む
- 3 つ揃ったら:
  1. 構造化された意図整理サマリーを出力する
  2. `update_field(field_name="意図分析", content=...)` を使って保存する
  3. 「✅ 意図整理を保存しました。ワークスペースで確認し、『続ける』で次へ進めます」と案内する
- この段階で別質問を受けた場合も通常どおり回答する
- ユーザーが「続ける」「次へ」と言った場合は、次に扱うノードをワークスペースで選ぶよう案内する
""",
        "outline.system": """あなたはコンテンツ設計の専門家です。プロジェクト情報に基づいて、構造化されたコンテンツアウトラインを作成してください。

## プロジェクト情報
- コンテンツ種別: {content_type}
- クリエイタープロファイル: {creator_profile}
- プロジェクト意図: {intent}
- 対象ユーザー: {research}

## アウトライン要件
{structure_hint}

代表的なセクション候補（必要に応じて調整可）: {typical_sections}

## 出力形式
以下の JSON 形式のみを出力してください。
```json
{{
    "title": "アウトラインタイトル",
    "summary": "アウトライン概要（1-2文）",
    "nodes": [
        {{
            "name": "セクション名",
            "description": "セクション説明",
            "ai_prompt": "このセクション生成用の AI プロンプト",
            "depends_on": ["依存する他セクション名"],
            "children": [
                {{
                    "name": "子セクション名",
                    "description": "子セクション説明",
                    "ai_prompt": "AI プロンプト",
                    "depends_on": []
                }}
            ]
        }}
    ]
}}
```

ルール:
1. 論理構造が明確であること
2. `ai_prompt` は具体的で生成指示として機能すること
3. `depends_on` には先行して必要なセクションを入れること
4. `children` は必要な場合のみ使うこと
5. プロジェクト特性に合わせて柔軟に設計すること

JSON 以外は出力しないでください。""",
        "outline.human": "コンテンツアウトラインを生成してください",
        "eval.persona.system": "あなたはペルソナ設計の専門家です。必ず JSON のみを出力し、余計な説明は書かないでください。",
        "eval.persona.user": """以下のプロジェクトに対して、新しいユーザーペルソナを 1 つ作成してください（既存名と重複しないこと）。

【プロジェクト名】
{project_name}

【プロジェクト意図】
{project_intent}

【既存ペルソナ名（重複禁止）】
{names_text}

出力 JSON:
{{"name":"ペルソナ名","prompt":"人物像、背景、主要ニーズ、懸念、意思決定基準を含む完全なペルソナ用プロンプト"}}""",
        "eval.persona.fallback_name": "新規ペルソナ",
        "eval.persona.fallback_prompt": "あなたは{name}です。プロジェクト目的を踏まえ、実在の顧客として率直なフィードバックを返してください。",
        "eval.persona.fallback_default": "あなたは見込み顧客です。コンテンツが本当に課題解決につながるか、コストに見合うか、実行可能かを重視して判断してください。",
        "eval.prompt.system": "あなたはプロンプト設計の専門家です。必ず JSON のみを出力し、余計な説明は書かないでください。",
        "eval.prompt.user": """以下の評価シナリオ向けプロンプトを作成してください。

【プロンプト種別】{prompt_type_name}
【評価形態】{form_type_name}
【役割 / シナリオ説明】{description}
【プロジェクト背景】{project_context}
【必須プレースホルダー】{required_placeholders}

要件:
1) 役割定義が明確であること
2) 行動要件が具体的であること
3) 採点シーンでは採点観点を含めること
4) 構造化 JSON 出力ルールを含めること
5) 必須プレースホルダーを保持すること

出力 JSON:
{{"generated_prompt":"完成プロンプト"}}""",
        "eval.prompt.fallback": "あなたは評価の専門家です。提示された内容を評価し、必ず JSON 形式で結果を返してください。",
        "eval_engine.review_default": "以下の内容を評価してください。",
        "eval.prompt.focus_header": "【今回の焦点】\n{probe}",
        "eval.experience.no_blocks": "探索できるコンテンツブロックがありません",
        "eval.experience.default_persona_prompt": "あなたは実在の消費者です。",
        "eval.experience.block_fallback_title": "コンテンツブロック{index}",
        "eval.experience.probe_section": "【あなたの重要な関心事】\n{probe}",
        "eval.experience.memory_none": "（なし）",
        "eval.experience.no_doubt": "特になし",
        "eval.experience.memory_line": "{block_title}：{doubt}（{score}点）",
        "eval.experience.stage_plan": "ステップ1-探索計画",
        "eval.experience.stage_per_block": "ステップ2-ブロック別探索",
        "eval.experience.stage_summary": "ステップ3-全体総括",
        "eval.experience.plan.system": "あなたは実在の消費者です。必ず JSON のみを出力し、余計な説明は書かないでください。",
        "eval.experience.plan.user": """【あなたの人物像】
{persona_prompt}

{probe_section}

いま確認できるコンテンツブロックは次のとおりです。
{block_list}

必ず次の JSON を出力してください（Markdown や解説は禁止）:
{{"plan":[{{"block_id":"id","block_title":"タイトル","reason":"なぜ先に見るか","expectation":"何を確認したいか"}}],"overall_goal":"1文の目的"}}

厳守事項:
1) plan は 3-5 ステップ必須。ブロック数が 3 未満なら、存在するブロックをすべて列挙すること。
2) 各ステップは上記一覧にある有効な block_id を必ず参照し、捏造しないこと。
3) 優先順位を断定しづらくても、暫定順序を提示し、省略しないこと。""",
        "eval.experience.per_block.system": "あなたは実在の消費者です。必ず指定どおり JSON で回答してください。",
        "eval.experience.per_block.user": """【あなたの人物像】
{persona_prompt}

{probe_section}

【ここまでの閲覧メモ】
{exploration_memory}

【現在のコンテンツブロック】
タイトル: {block_title}
内容:
{block_content}

必ず次の JSON を出力してください（Markdown や解説は禁止）:
{{"concern_match":"...","discovery":"...","doubt":"...","missing":"...","feeling":"{persona_name}としての率直な感想","score":1-10}}

厳守事項:
1) score は 1-10 の整数で必須。不確実なら控えめな点数にし、理由を doubt に書くこと。
2) missing には、追加してほしい具体情報・事例・手順だけを書くこと。抽象論は禁止。
3) discovery と doubt は必ずこのブロック内の記述に基づかせ、本文を離れた推測をしないこと。""",
        "eval.experience.summary.system": "あなたは実在の消費者です。必ず JSON のみで総括を返してください。",
        "eval.experience.summary.user": """【あなたの人物像】
{persona_prompt}

{probe_section}

以下はブロックごとの探索結果です。
{all_block_results}

必ず次の JSON を出力してください（Markdown や解説は禁止）:
{{"overall_impression":"...","concerns_addressed":[],"concerns_unaddressed":[],"would_recommend":true,"summary":"{persona_name}としての総合判断"}}

厳守事項:
1) concerns_addressed / concerns_unaddressed の各項目は、必ずブロック別結果の根拠を持つこと。
2) summary には「推薦するかどうか」と、その条件または見送る理由を必ず明記すること。
3) 情報不足がある場合は、concerns_unaddressed に不足点を明記すること。""",
    },
}


def rt_template(locale: str | None, key: str) -> str:
    normalized = normalize_locale(locale)
    return (
        RUNTIME_TEXTS.get(normalized, {}).get(key)
        or RUNTIME_TEXTS["zh-CN"].get(key, key)
    )


def rt(locale: str | None, key: str, **kwargs) -> str:
    template = rt_template(locale, key)
    return template.format(**kwargs)


def markdown_instructions(locale: str | None) -> str:
    return rt(locale, "markdown.instructions")
