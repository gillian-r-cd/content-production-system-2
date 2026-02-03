# backend/core/tools/simulator.py
# 功能: 消费者模拟工具
# 主要函数: run_simulation(), run_dialogue_simulation()
# 数据结构: SimulationResult

"""
消费者模拟工具
支持多种交互类型的模拟
"""

from typing import Optional
from dataclasses import dataclass, field

from core.ai_client import ai_client, ChatMessage
from core.models import Simulator, SimulationRecord, ProjectField


@dataclass
class SimulationFeedback:
    """模拟反馈"""
    scores: dict[str, float] = field(default_factory=dict)
    comments: dict[str, str] = field(default_factory=dict)
    overall: str = ""


@dataclass
class SimulationResult:
    """模拟结果"""
    record_id: str
    interaction_log: list[dict] | dict
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
            interaction_log={"input": content, "output": response.content},
            feedback=feedback,
            success=True,
        )
        
    except Exception as e:
        return SimulationResult(
            record_id="",
            interaction_log={},
            feedback=SimulationFeedback(),
            success=False,
            error=str(e),
        )


async def run_dialogue_simulation(
    simulator: Simulator,
    content: str,
    persona: dict,
    max_turns: int = 5,
) -> SimulationResult:
    """
    运行对话式模拟
    
    模拟一个消费者与内容/服务的多轮对话，然后评估对话质量。
    
    Args:
        simulator: 模拟器配置
        content: 初始内容/上下文（产品描述、服务介绍等）
        persona: 用户画像
        max_turns: 最大对话轮数
    
    Returns:
        SimulationResult 包含完整对话历史和评估反馈
    """
    prompt_template = simulator.prompt_template or Simulator.get_default_template("dialogue")
    
    persona_text = f"""
姓名: {persona.get('name', '匿名用户')}
背景: {persona.get('background', '')}
故事: {persona.get('story', '')}
"""
    
    # === 第一阶段：模拟消费者提问 ===
    consumer_system = f"""你是一位真实的消费者，具有以下特征：
{persona_text}

你正在了解一个产品/服务。请基于你的背景和需求，自然地提出问题。
每次只问一个问题，表达要简短自然，像真人一样。"""

    # === 第二阶段：模拟服务方回复 ===
    service_system = f"""你是这个产品/服务的AI助手。基于以下产品信息回复用户的问题：

{content}

要求：
1. 回答要基于产品信息，不要编造
2. 语气友好专业
3. 回答简洁明了"""

    interaction_log = []
    
    try:
        for turn in range(max_turns):
            # 消费者提问
            consumer_messages = [
                ChatMessage(role="system", content=consumer_system),
            ]
            # 加入对话历史
            for log in interaction_log:
                if log["role"] == "consumer":
                    consumer_messages.append(ChatMessage(role="assistant", content=log["content"]))
                else:
                    consumer_messages.append(ChatMessage(role="user", content=log["content"]))
            
            if turn == 0:
                consumer_messages.append(ChatMessage(
                    role="user", 
                    content="请开始提出你的第一个问题。"
                ))
            else:
                consumer_messages.append(ChatMessage(
                    role="user",
                    content="请基于之前的对话，继续提问或表达你的想法。如果觉得足够了解了，可以说'好的，我了解了'。"
                ))
            
            consumer_response = await ai_client.async_chat(consumer_messages, temperature=0.8)
            consumer_msg = consumer_response.content
            
            interaction_log.append({
                "role": "consumer",
                "content": consumer_msg,
                "turn": turn + 1,
            })
            
            # 检查是否结束
            if any(end_signal in consumer_msg for end_signal in ["了解了", "明白了", "好的谢谢", "再见", "不需要了"]):
                break
            
            # 服务方回复
            service_messages = [
                ChatMessage(role="system", content=service_system),
            ]
            for log in interaction_log:
                if log["role"] == "consumer":
                    service_messages.append(ChatMessage(role="user", content=log["content"]))
                else:
                    service_messages.append(ChatMessage(role="assistant", content=log["content"]))
            
            service_response = await ai_client.async_chat(service_messages, temperature=0.7)
            service_msg = service_response.content
            
            interaction_log.append({
                "role": "service",
                "content": service_msg,
                "turn": turn + 1,
            })
        
        # === 第三阶段：生成评估反馈 ===
        dialogue_transcript = "\n".join([
            f"{'[消费者]' if log['role'] == 'consumer' else '[服务方]'}: {log['content']}"
            for log in interaction_log
        ])
        
        dimensions = simulator.evaluation_dimensions or ["响应相关性", "问题解决率", "交互体验"]
        
        eval_system = f"""你是{persona.get('name', '这位消费者')}，刚刚与一个产品/服务进行了对话。

你的背景：
{persona_text}

请基于你的真实感受评估这次对话体验。"""

        eval_instruction = f"""以下是对话记录：

{dialogue_transcript}

请以这位消费者的身份，评估这次对话体验：

以JSON格式输出：
{{
    "scores": {{{", ".join([f'"{d}": 分数(1-10)' for d in dimensions])}}},
    "comments": {{{", ".join([f'"{d}": "具体评语"' for d in dimensions])}}},
    "questions_answered": ["被解答的问题1", "..."],
    "questions_unanswered": ["未解答的问题1", "..."],
    "friction_points": ["交互中的摩擦点1", "..."],
    "would_continue": true/false,
    "overall": "总体评价（100字以内）"
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
                "questions_answered": ", ".join(feedback_data.get("questions_answered", [])),
                "questions_unanswered": ", ".join(feedback_data.get("questions_unanswered", [])),
                "friction_points": ", ".join(feedback_data.get("friction_points", [])),
                "would_continue": str(feedback_data.get("would_continue", "unknown")),
            },
            overall=feedback_data.get("overall", ""),
        )
        
        return SimulationResult(
            record_id="",
            interaction_log=interaction_log,
            feedback=feedback,
            success=True,
        )
        
    except Exception as e:
        return SimulationResult(
            record_id="",
            interaction_log=interaction_log,
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
            interaction_log=feedback_data,
            feedback=feedback,
            success=True,
        )
        
    except Exception as e:
        return SimulationResult(
            record_id="",
            interaction_log={},
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
            interaction_log={"task": task},
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
                "task": task,
                "steps": feedback_data.get("steps", []),
                "time_estimate": feedback_data.get("time_estimate", ""),
                "suggestions": feedback_data.get("suggestions", []),
            },
            feedback=feedback,
            success=True,
        )
        
    except Exception as e:
        return SimulationResult(
            record_id="",
            interaction_log={"task": task},
            feedback=SimulationFeedback(),
            success=False,
            error=str(e),
        )


async def run_simulation(
    simulator: Simulator,
    content: str,
    persona: dict,
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
    
    Returns:
        SimulationResult
    """
    sim_type = simulator.interaction_type
    
    if sim_type == "reading":
        return await run_reading_simulation(simulator, content, persona)
    elif sim_type == "dialogue":
        max_turns = simulator.max_turns or 5
        return await run_dialogue_simulation(simulator, content, persona, max_turns)
    elif sim_type == "decision":
        return await run_decision_simulation(simulator, content, persona)
    elif sim_type == "exploration":
        return await run_exploration_simulation(simulator, content, persona)
    elif sim_type == "experience":
        return await run_experience_simulation(simulator, content, persona)
    else:
        # 默认使用阅读式
        return await run_reading_simulation(simulator, content, persona)

