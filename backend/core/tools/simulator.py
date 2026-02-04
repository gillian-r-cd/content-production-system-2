# backend/core/tools/simulator.py
# 功能: 消费者模拟工具
# 主要函数: run_simulation(), run_dialogue_simulation()
# 数据结构: SimulationResult

"""
消费者模拟工具
支持多种交互类型的模拟
"""

from typing import Optional, Dict, List, Union
from dataclasses import dataclass, field

from core.ai_client import ai_client, ChatMessage
from core.models import Simulator, SimulationRecord, ProjectField


@dataclass
class SimulationFeedback:
    """模拟反馈"""
    scores: Dict[str, float] = field(default_factory=dict)
    comments: Dict[str, str] = field(default_factory=dict)
    overall: str = ""


@dataclass
class SimulationResult:
    """模拟结果"""
    record_id: str
    interaction_log: Union[List[dict], dict]
    feedback: SimulationFeedback
    success: bool
    error: Optional[str] = None


async def run_reading_simulation(
    simulator: Simulator,
    content: str,
    persona: dict,
) -> SimulationResult:
    """
    运行阅读式模拟
    
    Args:
        simulator: 模拟器配置
        content: 要评估的内容
        persona: 用户画像
    
    Returns:
        SimulationResult
    """
    # 构建提示词
    prompt_template = simulator.prompt_template or Simulator.get_default_template("reading")
    
    persona_text = f"""
姓名: {persona.get('name', '匿名用户')}
背景: {persona.get('background', '')}
故事: {persona.get('story', '')}
"""
    
    system_prompt = prompt_template.format(
        persona=persona_text,
        content=content,
    )
    
    # 构建评估指令
    dimensions = simulator.evaluation_dimensions or ["理解难度", "价值感知", "行动意愿"]
    eval_instruction = f"""
请以JSON格式输出你的反馈：
{{
    "scores": {{{", ".join([f'"{d}": 分数(1-10)' for d in dimensions])}}},
    "comments": {{{", ".join([f'"{d}": "评语"' for d in dimensions])}}},
    "overall": "总体评价（100字以内）"
}}
"""
    
    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=eval_instruction),
    ]
    
    try:
        response = await ai_client.async_chat(messages, temperature=0.7)
        
        # 解析反馈
        import json
        feedback_data = json.loads(response.content)
        feedback = SimulationFeedback(
            scores=feedback_data.get("scores", {}),
            comments=feedback_data.get("comments", {}),
            overall=feedback_data.get("overall", ""),
        )
        
        return SimulationResult(
            record_id="",
            interaction_log={
                "input": content,
                "system_prompt": system_prompt,
                "user_instruction": eval_instruction,
                "output": response.content,
            },
            feedback=feedback,
            success=True,
        )
        
    except Exception as e:
        return SimulationResult(
            record_id="",
            interaction_log={
                "input": content,
                "system_prompt": system_prompt,
                "error": str(e),
            },
            feedback=SimulationFeedback(),
            success=False,
            error=str(e),
        )


async def run_dialogue_simulation(
    simulator: Simulator,
    content: str,
    persona: dict,
    max_turns: int = 5,
    content_field_names: list = None,  # 新增：内容字段名称列表
) -> SimulationResult:
    """
    运行对话式模拟
    
    模拟场景：一个真实用户（Persona）带着问题/困惑，与"内容"进行对话。
    验证目标：内容能否回答用户的问题、解决用户的困惑、让用户感到有价值。
    
    核心设计：
    1. 用户（Persona）：带着背景、需求、痛点来咨询
    2. 内容代表：严格基于提供的内容回答，不能编造
    3. 知识边界：如果内容中没有相关信息，要诚实说"这个问题在内容中没有涉及"
    
    Args:
        simulator: 模拟器配置
        content: 内容（选定字段的内容）
        persona: 用户画像
        max_turns: 最大对话轮数
        content_field_names: 内容来源字段名称（用于显示）
    
    Returns:
        SimulationResult 包含完整对话历史和评估反馈
    """
    # === 角色名称 ===
    user_name = persona.get('name', '用户')
    content_name = "内容"
    if content_field_names:
        if len(content_field_names) == 1:
            content_name = f"《{content_field_names[0]}》"
        else:
            content_name = f"《{content_field_names[0]}》等{len(content_field_names)}篇内容"
    
    persona_text = f"""姓名: {user_name}
背景: {persona.get('background', '')}
详细情况: {persona.get('story', '')}"""
    
    # === 模拟用户的系统提示词 ===
    user_system = f"""你正在扮演一位真实用户进行模拟对话。

【你的角色】
{persona_text}

【你的目标】
你有一些困惑和问题想要解决。你正在通过阅读/咨询{content_name}来寻找答案。
请基于你的背景和真实需求，自然地提出问题。

【行为要求】
1. 每次只问一个问题，表达简短自然
2. 问题要基于你的真实背景和痛点
3. 如果对方的回答让你满意或困惑得到解决，可以表示感谢并结束
4. 如果对方的回答不能解决你的问题，继续追问或换个角度问
5. 如果觉得已经了解足够了，说"好的，我了解了，谢谢"结束对话"""

    # === 内容代表的系统提示词（严格知识边界）===
    content_system = f"""你是{content_name}的内容代表，负责回答用户基于这些内容的问题。

【重要：知识边界约束】
你只能基于以下内容来回答问题。这是你的全部知识，不能编造或推测内容以外的信息。

=== 内容开始 ===
{content}
=== 内容结束 ===

【回答规则】
1. **严格基于内容回答**：只能使用上述内容中明确提到的信息
2. **诚实承认不足**：如果内容中没有涉及用户的问题，请诚实说"这个问题在当前内容中没有详细说明"
3. **不要编造**：宁可说"不知道"也不要编造内容中没有的信息
4. **引用内容**：尽量引用内容中的原话或核心观点
5. **语气友好**：像一位了解这些内容的朋友在解答

【回答示例】
- 好的回答："根据内容中提到的，XXX可以通过YYY来解决..."
- 好的回答："这个问题内容中提到了一个方法：..."
- 诚实的回答："关于这个具体问题，当前内容没有直接给出答案，但提到了相关的XXX..."
- 不好的回答：编造内容中没有的信息"""

    interaction_log = []
    
    try:
        for turn in range(max_turns):
            # === 用户提问 ===
            user_messages = [
                ChatMessage(role="system", content=user_system),
            ]
            # 加入对话历史（从用户视角）
            for log in interaction_log:
                if log["role"] == "user":
                    user_messages.append(ChatMessage(role="assistant", content=log["content"]))
                else:
                    user_messages.append(ChatMessage(role="user", content=log["content"]))
            
            if turn == 0:
                user_messages.append(ChatMessage(
                    role="user", 
                    content="请基于你的背景，提出你最想解决的第一个问题。"
                ))
            else:
                user_messages.append(ChatMessage(
                    role="user",
                    content="请基于之前的对话，继续你的咨询。你可以追问、换个问题、或者如果满意了就结束对话。"
                ))
            
            user_response = await ai_client.async_chat(user_messages, temperature=0.8)
            user_msg = user_response.content
            
            interaction_log.append({
                "role": "user",
                "name": user_name,
                "content": user_msg,
                "turn": turn + 1,
            })
            
            # 检查是否结束
            end_signals = ["了解了", "明白了", "好的谢谢", "谢谢", "再见", "不需要了", "足够了", "清楚了"]
            if any(end_signal in user_msg for end_signal in end_signals):
                break
            
            # === 内容代表回复 ===
            content_messages = [
                ChatMessage(role="system", content=content_system),
            ]
            for log in interaction_log:
                if log["role"] == "user":
                    content_messages.append(ChatMessage(role="user", content=log["content"]))
                else:
                    content_messages.append(ChatMessage(role="assistant", content=log["content"]))
            
            content_response = await ai_client.async_chat(content_messages, temperature=0.5)
            content_msg = content_response.content
            
            interaction_log.append({
                "role": "content",
                "name": content_name,
                "content": content_msg,
                "turn": turn + 1,
            })
        
        # === 评估阶段 ===
        dialogue_transcript = "\n".join([
            f"[{log.get('name', log['role'])}]: {log['content']}"
            for log in interaction_log
        ])
        
        dimensions = simulator.evaluation_dimensions or ["问题解决度", "内容价值感", "信息完整性"]
        
        eval_system = f"""你是{user_name}，刚刚与{content_name}进行了一次咨询对话。

你的背景：
{persona_text}

请以你的真实身份，评估这次对话中**内容**对你的帮助程度。
注意：评估的是**内容本身的价值**，不是AI的回答技巧。"""

        eval_instruction = f"""以下是对话记录：

{dialogue_transcript}

请评估：这些内容是否解决了你的问题？对你有多大价值？

以JSON格式输出：
{{
    "scores": {{{", ".join([f'"{d}": 分数(1-10)' for d in dimensions])}}},
    "comments": {{{", ".join([f'"{d}": "具体评语"' for d in dimensions])}}},
    "problems_solved": ["被解决的问题/困惑1", "..."],
    "problems_unsolved": ["未被解决的问题/困惑1", "..."],
    "content_gaps": ["内容缺失的部分1", "..."],
    "valuable_points": ["内容中最有价值的点1", "..."],
    "would_recommend": true/false,
    "overall": "总体评价：这些内容对你的帮助程度（100字以内）"
}}"""

        eval_messages = [
            ChatMessage(role="system", content=eval_system),
            ChatMessage(role="user", content=eval_instruction),
        ]
        
        eval_response = await ai_client.async_chat(eval_messages, temperature=0.5)
        
        import json
        feedback_data = json.loads(eval_response.content)
        
        feedback = SimulationFeedback(
            scores=feedback_data.get("scores", {}),
            comments={
                **feedback_data.get("comments", {}),
                "problems_solved": ", ".join(feedback_data.get("problems_solved", [])),
                "problems_unsolved": ", ".join(feedback_data.get("problems_unsolved", [])),
                "content_gaps": ", ".join(feedback_data.get("content_gaps", [])),
                "valuable_points": ", ".join(feedback_data.get("valuable_points", [])),
                "would_recommend": str(feedback_data.get("would_recommend", "unknown")),
            },
            overall=feedback_data.get("overall", ""),
        )
        
        return SimulationResult(
            record_id="",
            interaction_log={
                "type": "dialogue",
                "user_name": user_name,
                "content_name": content_name,
                "user_system_prompt": user_system,
                "content_system_prompt": content_system,
                "eval_system_prompt": eval_system,
                "dialogue": interaction_log,
                "eval_output": eval_response.content,
            },
            feedback=feedback,
            success=True,
        )
        
    except Exception as e:
        return SimulationResult(
            record_id="",
            interaction_log={
                "type": "dialogue",
                "user_name": user_name,
                "content_name": content_name,
                "user_system_prompt": user_system,
                "content_system_prompt": content_system,
                "dialogue": interaction_log,
                "error": str(e),
            },
            feedback=SimulationFeedback(),
            success=False,
            error=str(e),
        )


async def run_decision_simulation(
    simulator: Simulator,
    content: str,
    persona: dict,
) -> SimulationResult:
    """
    运行决策式模拟
    
    Args:
        simulator: 模拟器配置
        content: 销售页/落地页内容
        persona: 用户画像
    
    Returns:
        SimulationResult
    """
    prompt_template = simulator.prompt_template or Simulator.get_default_template("decision")
    
    persona_text = f"""
姓名: {persona.get('name', '匿名用户')}
背景: {persona.get('background', '')}
故事: {persona.get('story', '')}
"""
    
    system_prompt = prompt_template.format(
        persona=persona_text,
        content=content,
    )
    
    dimensions = simulator.evaluation_dimensions or ["转化意愿", "顾虑点", "信任度"]
    eval_instruction = f"""
请以JSON格式输出你的决策过程和反馈：
{{
    "first_impression": "第一印象",
    "attractive_points": ["吸引点1", "吸引点2"],
    "concerns": ["顾虑1", "顾虑2"],
    "decision": "会购买/不会购买",
    "reason": "原因",
    "scores": {{{", ".join([f'"{d}": 分数(1-10)' for d in dimensions])}}},
    "overall": "总体评价"
}}
"""
    
    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=eval_instruction),
    ]
    
    try:
        response = await ai_client.async_chat(messages, temperature=0.7)
        
        import json
        feedback_data = json.loads(response.content)
        feedback = SimulationFeedback(
            scores=feedback_data.get("scores", {}),
            comments={
                "first_impression": feedback_data.get("first_impression", ""),
                "decision": feedback_data.get("decision", ""),
                "reason": feedback_data.get("reason", ""),
            },
            overall=feedback_data.get("overall", ""),
        )
        
        return SimulationResult(
            record_id="",
            interaction_log={
                "type": "decision",
                "input": content,
                "system_prompt": system_prompt,
                "user_instruction": eval_instruction,
                "output": response.content,
                "decision_details": feedback_data,
            },
            feedback=feedback,
            success=True,
        )
        
    except Exception as e:
        return SimulationResult(
            record_id="",
            interaction_log={
                "type": "decision",
                "input": content,
                "system_prompt": system_prompt,
                "error": str(e),
            },
            feedback=SimulationFeedback(),
            success=False,
            error=str(e),
        )


async def run_exploration_simulation(
    simulator: Simulator,
    content: str,
    persona: dict,
    task: str = "",
) -> SimulationResult:
    """
    运行探索式模拟
    
    模拟用户带着特定目的在内容中寻找答案的过程。
    
    Args:
        simulator: 模拟器配置
        content: 文档/帮助内容
        persona: 用户画像
        task: 用户要完成的任务/要解决的问题
    
    Returns:
        SimulationResult
    """
    prompt_template = simulator.prompt_template or Simulator.get_default_template("exploration")
    
    persona_text = f"""
姓名: {persona.get('name', '匿名用户')}
背景: {persona.get('background', '')}
故事: {persona.get('story', '')}
"""
    
    # 如果没有指定任务，根据persona生成一个
    if not task:
        task = persona.get("task", "找到这个产品的核心功能和使用方法")
    
    system_prompt = f"""你是一位真实的用户，具有以下特征：
{persona_text}

你有一个具体问题需要解决：{task}

请模拟你在以下文档中寻找答案的过程。记录：
1. 你会如何浏览这些内容
2. 哪些部分吸引了你的注意
3. 你是否找到了答案
4. 遇到了什么困难"""

    dimensions = simulator.evaluation_dimensions or ["找到答案效率", "信息完整性", "满意度"]
    
    eval_instruction = f"""以下是你要浏览的文档内容：

{content}

请模拟你的探索过程，然后以JSON格式输出：
{{
    "exploration_path": ["首先看了...", "然后...", "..."],
    "attention_points": ["吸引注意的内容1", "..."],
    "found_answer": true/false,
    "answer_location": "在哪里找到的答案（如果找到）",
    "difficulties": ["遇到的困难1", "..."],
    "missing_info": ["缺失的信息1", "..."],
    "scores": {{{", ".join([f'"{d}": 分数(1-10)' for d in dimensions])}}},
    "comments": {{{", ".join([f'"{d}": "评语"' for d in dimensions])}}},
    "overall": "总体评价"
}}"""

    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=eval_instruction),
    ]
    
    try:
        response = await ai_client.async_chat(messages, temperature=0.7)
        
        import json
        feedback_data = json.loads(response.content)
        
        feedback = SimulationFeedback(
            scores=feedback_data.get("scores", {}),
            comments={
                **feedback_data.get("comments", {}),
                "found_answer": str(feedback_data.get("found_answer", False)),
                "difficulties": ", ".join(feedback_data.get("difficulties", [])),
                "missing_info": ", ".join(feedback_data.get("missing_info", [])),
            },
            overall=feedback_data.get("overall", ""),
        )
        
        return SimulationResult(
            record_id="",
            interaction_log={
                "type": "exploration",
                "input": content,
                "system_prompt": system_prompt,
                "user_instruction": eval_instruction,
                "output": response.content,
                "task": task,
                "exploration_path": feedback_data.get("exploration_path", []),
                "attention_points": feedback_data.get("attention_points", []),
                "answer_location": feedback_data.get("answer_location", ""),
            },
            feedback=feedback,
            success=True,
        )
        
    except Exception as e:
        return SimulationResult(
            record_id="",
            interaction_log={
                "type": "exploration",
                "input": content,
                "system_prompt": system_prompt,
                "task": task,
                "error": str(e),
            },
            feedback=SimulationFeedback(),
            success=False,
            error=str(e),
        )


async def run_experience_simulation(
    simulator: Simulator,
    content: str,
    persona: dict,
    task: str = "",
) -> SimulationResult:
    """
    运行体验式模拟
    
    模拟用户使用产品完成特定任务的过程。
    
    Args:
        simulator: 模拟器配置
        content: 产品/工具描述
        persona: 用户画像
        task: 要完成的任务
    
    Returns:
        SimulationResult
    """
    prompt_template = simulator.prompt_template or Simulator.get_default_template("experience")
    
    persona_text = f"""
姓名: {persona.get('name', '匿名用户')}
背景: {persona.get('background', '')}
故事: {persona.get('story', '')}
"""
    
    if not task:
        task = persona.get("task", "完成产品的核心功能体验")
    
    system_prompt = f"""你是一位真实的用户，具有以下特征：
{persona_text}

你需要使用以下产品/工具完成一个任务：{task}

产品信息：
{content}

请模拟你的使用体验过程，包括：
1. 你会如何开始
2. 使用过程中的每个步骤
3. 遇到的问题和解决方式
4. 最终是否完成任务"""

    dimensions = simulator.evaluation_dimensions or ["易用性", "效率", "愉悦度"]
    
    eval_instruction = f"""请模拟你的完整体验过程，然后以JSON格式输出：
{{
    "steps": [
        {{"step": 1, "action": "做了什么", "result": "结果如何", "feeling": "感受"}},
        ...
    ],
    "task_completed": true/false,
    "time_estimate": "预计花费时间",
    "pain_points": ["痛点1", "..."],
    "delights": ["惊喜点1", "..."],
    "suggestions": ["改进建议1", "..."],
    "scores": {{{", ".join([f'"{d}": 分数(1-10)' for d in dimensions])}}},
    "comments": {{{", ".join([f'"{d}": "评语"' for d in dimensions])}}},
    "would_recommend": true/false,
    "overall": "总体评价"
}}"""

    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=eval_instruction),
    ]
    
    try:
        response = await ai_client.async_chat(messages, temperature=0.7)
        
        import json
        feedback_data = json.loads(response.content)
        
        feedback = SimulationFeedback(
            scores=feedback_data.get("scores", {}),
            comments={
                **feedback_data.get("comments", {}),
                "task_completed": str(feedback_data.get("task_completed", False)),
                "pain_points": ", ".join(feedback_data.get("pain_points", [])),
                "delights": ", ".join(feedback_data.get("delights", [])),
                "would_recommend": str(feedback_data.get("would_recommend", False)),
            },
            overall=feedback_data.get("overall", ""),
        )
        
        return SimulationResult(
            record_id="",
            interaction_log={
                "type": "experience",
                "input": content,
                "system_prompt": system_prompt,
                "user_instruction": eval_instruction,
                "output": response.content,
                "task": task,
                # 完整保存所有结构化数据
                "steps": feedback_data.get("steps", []),
                "time_estimate": feedback_data.get("time_estimate", ""),
                "task_completed": feedback_data.get("task_completed", False),
                "pain_points": feedback_data.get("pain_points", []),
                "delights": feedback_data.get("delights", []),
                "suggestions": feedback_data.get("suggestions", []),
                "would_recommend": feedback_data.get("would_recommend", False),
            },
            feedback=feedback,
            success=True,
        )
        
    except Exception as e:
        return SimulationResult(
            record_id="",
            interaction_log={
                "type": "experience",
                "input": content,
                "system_prompt": system_prompt,
                "task": task,
                "error": str(e),
            },
            feedback=SimulationFeedback(),
            success=False,
            error=str(e),
        )


async def run_simulation(
    simulator: Simulator,
    content: str,
    persona: dict,
    content_field_names: list = None,  # 新增：内容字段名称列表
) -> SimulationResult:
    """
    运行模拟（自动选择类型）
    
    根据 simulator.interaction_type 选择对应的模拟方式：
    - reading: 阅读式 - 阅读全部内容后给出反馈
    - dialogue: 对话式 - 多轮对话后评估交互质量
    - decision: 决策式 - 模拟购买决策过程
    - exploration: 探索式 - 带目的的内容探索
    - experience: 体验式 - 任务完成模拟
    
    Args:
        simulator: 模拟器配置
        content: 内容
        persona: 用户画像
        content_field_names: 内容来源字段名称（用于日志和提示词显示）
    
    Returns:
        SimulationResult
    """
    sim_type = simulator.interaction_type
    
    if sim_type == "reading":
        return await run_reading_simulation(simulator, content, persona)
    elif sim_type == "dialogue":
        max_turns = simulator.max_turns or 5
        return await run_dialogue_simulation(
            simulator, content, persona, max_turns, content_field_names
        )
    elif sim_type == "decision":
        return await run_decision_simulation(simulator, content, persona)
    elif sim_type == "exploration":
        return await run_exploration_simulation(simulator, content, persona)
    elif sim_type == "experience":
        return await run_experience_simulation(simulator, content, persona)
    else:
        # 默认使用阅读式
        return await run_reading_simulation(simulator, content, persona)

