# backend/core/tools/evaluator.py
# 功能: 评估工具
# 主要函数: evaluate_project(), evaluate_section()
# 数据结构: EvaluationResult

"""
评估工具
根据评估模板对项目进行全面评估
"""

from typing import Optional, Dict, List
from dataclasses import dataclass, field
from pydantic import BaseModel, Field as PydanticField

from core.ai_client import ai_client, ChatMessage
from core.models import (
    Project,
    ProjectField,
    EvaluationTemplate,
    SimulationRecord,
)


class SectionScore(BaseModel):
    """板块评分"""
    scores: Dict[str, float] = PydanticField(description="各指标评分")
    comments: Dict[str, str] = PydanticField(description="各指标评语")
    summary: str = PydanticField(description="板块总结")


class Suggestion(BaseModel):
    """修改建议"""
    id: str = PydanticField(description="建议ID")
    section_id: str = PydanticField(description="相关板块")
    content: str = PydanticField(description="建议内容")
    priority: str = PydanticField(description="优先级: high/medium/low")
    actionable: bool = PydanticField(default=True, description="是否可操作")


class EvaluationResult(BaseModel):
    """评估结果"""
    section_scores: Dict[str, SectionScore] = PydanticField(description="各板块评分")
    overall_score: float = PydanticField(description="综合评分")
    suggestions: List[Suggestion] = PydanticField(description="修改建议")
    summary: str = PydanticField(description="总体评价")


async def evaluate_section(
    section: dict,
    project_context: str,
    fields_content: str,
    simulation_summary: Optional[str] = None,
) -> SectionScore:
    """
    评估单个板块
    
    Args:
        section: 评估板块配置
        project_context: 项目上下文（意图+用户画像）
        fields_content: 要评估的内容
        simulation_summary: 模拟结果汇总（如有）
    
    Returns:
        SectionScore
    """
    grader_prompt = section.get("grader_prompt", "请评估以下内容的质量。")
    metrics = section.get("metrics", [])
    
    # 构建评分指令
    metrics_instruction = "\n".join([
        f"- {m['name']}: {'1-10分' if m.get('type') == 'score_1_10' else '文本描述'}"
        for m in metrics
    ])
    
    context = f"""# 项目上下文
{project_context}

# 要评估的内容
{fields_content}
"""
    
    if simulation_summary:
        context += f"\n# 消费者模拟反馈\n{simulation_summary}"
    
    messages = [
        ChatMessage(
            role="system",
            content=f"""{grader_prompt}

请评估以下指标：
{metrics_instruction}

输出JSON格式：
{{
    "scores": {{"指标名": 分数, ...}},
    "comments": {{"指标名": "评语", ...}},
    "summary": "板块总结"
}}"""
        ),
        ChatMessage(role="user", content=context),
    ]
    
    score, _ = await ai_client.generate_structured(
        messages=messages,
        response_model=SectionScore,
        temperature=0.5,
    )
    
    return score


async def generate_suggestions(
    section_scores: Dict[str, SectionScore],
    project_context: str,
) -> List[Suggestion]:
    """
    生成修改建议
    
    Args:
        section_scores: 各板块评分
        project_context: 项目上下文
    
    Returns:
        建议列表
    """
    # 汇总评分情况
    scores_summary = "\n".join([
        f"## {section_id}\n评分: {score.scores}\n总结: {score.summary}"
        for section_id, score in section_scores.items()
    ])
    
    messages = [
        ChatMessage(
            role="system",
            content="""你是一个资深的内容评审专家。基于评估结果，生成具体的、可操作的修改建议。

要求：
1. 建议要具体，指出问题和解决方案
2. 按优先级排序（high > medium > low）
3. 每个建议都要可执行

输出JSON格式：
{
    "suggestions": [
        {
            "id": "s1",
            "section_id": "相关板块ID",
            "content": "具体建议内容",
            "priority": "high/medium/low",
            "actionable": true
        }
    ]
}"""
        ),
        ChatMessage(
            role="user",
            content=f"""# 项目上下文
{project_context}

# 评估结果
{scores_summary}

请生成修改建议："""
        ),
    ]
    
    class SuggestionList(BaseModel):
        suggestions: List[Suggestion]
    
    result, _ = await ai_client.generate_structured(
        messages=messages,
        response_model=SuggestionList,
        temperature=0.7,
    )
    
    return result.suggestions


async def evaluate_project(
    template: EvaluationTemplate,
    project: Project,
    fields: List[ProjectField],
    simulation_records: List[SimulationRecord],
    project_context: str,
) -> EvaluationResult:
    """
    评估整个项目
    
    Args:
        template: 评估模板
        project: 项目
        fields: 项目字段列表
        simulation_records: 模拟记录列表
        project_context: 项目上下文（Golden Context）
    
    Returns:
        EvaluationResult
    """
    # 准备内容
    fields_content = "\n\n".join([
        f"## {f.name}\n{f.content}"
        for f in fields if f.content
    ])
    
    # 准备模拟汇总 - 包含完整对话历史
    simulation_summary = None
    if simulation_records:
        sim_parts = []
        for idx, record in enumerate(simulation_records):
            feedback = record.feedback
            interaction_log = record.interaction_log
            
            sim_part = f"## 模拟 {idx + 1}: {record.persona.get('name', '匿名用户')}\n"
            
            # 如果是对话式，包含对话历史
            if isinstance(interaction_log, list) and len(interaction_log) > 0:
                first_item = interaction_log[0] if interaction_log else {}
                if "role" in first_item:
                    sim_part += "### 对话记录:\n"
                    for log in interaction_log:
                        role_name = "[消费者]" if log.get("role") == "consumer" else "[服务方]"
                        sim_part += f"{role_name}: {log.get('content', '')}\n"
                    sim_part += "\n"
            
            # 包含评分和反馈
            if feedback.get("scores"):
                avg_score = sum(feedback["scores"].values()) / len(feedback["scores"])
                sim_part += f"平均分: {avg_score:.1f}\n"
                for dim, score in feedback["scores"].items():
                    sim_part += f"- {dim}: {score}\n"
            
            if feedback.get("overall"):
                sim_part += f"总评: {feedback['overall']}\n"
            
            # 包含详细评语
            if feedback.get("comments"):
                comments = feedback["comments"]
                if comments.get("questions_unanswered"):
                    sim_part += f"未解答问题: {comments['questions_unanswered']}\n"
                if comments.get("friction_points"):
                    sim_part += f"摩擦点: {comments['friction_points']}\n"
                if comments.get("pain_points"):
                    sim_part += f"痛点: {comments['pain_points']}\n"
            
            sim_parts.append(sim_part)
        
        if sim_parts:
            simulation_summary = "\n---\n".join(sim_parts)
    
    # 逐板块评估
    section_scores = {}
    for section in template.sections:
        section_id = section.get("id", "unknown")
        
        # 检查是否从模拟记录获取
        if section.get("source") == "simulation_records":
            if simulation_records:
                # 汇总模拟分数
                all_scores = {}
                for record in simulation_records:
                    for k, v in record.feedback.get("scores", {}).items():
                        if k not in all_scores:
                            all_scores[k] = []
                        all_scores[k].append(v)
                
                avg_scores = {k: sum(v)/len(v) for k, v in all_scores.items()}
                
                section_scores[section_id] = SectionScore(
                    scores=avg_scores,
                    comments={"来源": "消费者模拟汇总"},
                    summary=f"基于{len(simulation_records)}次模拟的平均结果",
                )
            continue
        
        # 正常评估
        score = await evaluate_section(
            section=section,
            project_context=project_context,
            fields_content=fields_content,
            simulation_summary=simulation_summary,
        )
        section_scores[section_id] = score
    
    # 计算综合评分（加权平均）
    total_score = 0.0
    total_weight = 0.0
    for section in template.sections:
        section_id = section.get("id")
        weight = section.get("weight", 0)
        if section_id in section_scores:
            scores = section_scores[section_id].scores
            if scores:
                avg = sum(scores.values()) / len(scores)
                total_score += avg * weight
                total_weight += weight
    
    overall_score = total_score / total_weight if total_weight > 0 else 0.0
    
    # 生成建议
    suggestions = await generate_suggestions(section_scores, project_context)
    
    # 生成总结
    summary_parts = [f"综合评分: {overall_score:.1f}/10"]
    for section_id, score in section_scores.items():
        summary_parts.append(f"- {section_id}: {score.summary}")
    
    return EvaluationResult(
        section_scores=section_scores,
        overall_score=round(overall_score, 2),
        suggestions=suggestions,
        summary="\n".join(summary_parts),
    )

