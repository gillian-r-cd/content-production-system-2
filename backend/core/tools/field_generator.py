# backend/core/tools/field_generator.py
# 功能: 字段生成工具
# 主要函数: generate_field(), generate_fields_batch()
# 数据结构: FieldGenerationResult

"""
字段生成工具
根据提示词和上下文生成字段内容
支持流式输出和批量并行生成
"""

from typing import AsyncGenerator, Optional, List
from dataclasses import dataclass

from langchain_core.messages import SystemMessage, HumanMessage

from core.llm import get_chat_model
from core.llm_compat import normalize_content, resolve_model
from core.prompt_engine import prompt_engine, PromptContext
# 鸭子类型 — 函数接受任何有 .id/.name/.content/.ai_prompt 的对象（实际只传 ContentBlock）


@dataclass
class FieldGenerationResult:
    """字段生成结果"""
    field_id: str
    content: str
    success: bool
    error: Optional[str] = None


async def generate_field(
    field,  # ContentBlock（鸭子类型：需要 .id/.name/.content/.ai_prompt）
    context: PromptContext,
    temperature: float = 0.7,
    model: Optional[str] = None,
) -> FieldGenerationResult:
    """
    生成单个字段内容
    
    Args:
        field: 要生成的字段
        context: 提示词上下文
        temperature: 温度
        model: 显式指定模型名（如 block.model_override），为 None 时走 resolve_model 覆盖链
    
    Returns:
        FieldGenerationResult
    """
    try:
        # 构建完整提示词
        system_prompt = prompt_engine.get_field_generation_prompt(field, context)
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"请生成「{field.name}」的内容。"),
        ]
        
        # 按覆盖链解析模型
        effective_model = resolve_model(model_override=model or getattr(field, 'model_override', None))
        chat_model = get_chat_model(model=effective_model, temperature=temperature)
        response = await chat_model.ainvoke(messages)
        
        return FieldGenerationResult(
            field_id=field.id,
            content=normalize_content(response.content),
            success=True,
        )
        
    except Exception as e:
        return FieldGenerationResult(
            field_id=field.id,
            content="",
            success=False,
            error=str(e),
        )


async def generate_field_stream(
    field,  # ContentBlock（鸭子类型）
    context: PromptContext,
    temperature: float = 0.7,
    model: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """
    流式生成字段内容
    
    Args:
        field: 要生成的字段
        context: 提示词上下文
        temperature: 温度
        model: 显式指定模型名，为 None 时走 resolve_model 覆盖链
    
    Yields:
        内容片段
    """
    system_prompt = prompt_engine.get_field_generation_prompt(field, context)
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"请生成「{field.name}」的内容。"),
    ]
    
    effective_model = resolve_model(model_override=model or getattr(field, 'model_override', None))
    chat_model = get_chat_model(model=effective_model, temperature=temperature)
    async for chunk in chat_model.astream(messages):
        piece = normalize_content(chunk.content)
        if piece:
            yield piece


async def generate_fields_parallel(
    fields: List,  # ContentBlock（鸭子类型：需要 .id/.name/.content/.ai_prompt）
    context: PromptContext,
    temperature: float = 0.7,
) -> List[FieldGenerationResult]:
    """
    并行生成多个字段
    
    Args:
        fields: 字段列表
        context: 提示词上下文
        temperature: 温度
    
    Returns:
        生成结果列表
    """
    import asyncio
    
    tasks = [
        generate_field(field, context, temperature)
        for field in fields
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 处理异常
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            processed_results.append(FieldGenerationResult(
                field_id=fields[i].id,
                content="",
                success=False,
                error=str(result),
            ))
        else:
            processed_results.append(result)
    
    return processed_results


def resolve_field_order(fields: List) -> List[List]:
    """
    解析字段依赖顺序，返回可并行执行的分组
    
    Args:
        fields: 字段列表
    
    Returns:
        并行分组列表，如 [[A], [B, C], [D]] 表示A先执行，BC并行，最后D
    """
    # 构建ID到字段的映射
    field_by_id = {f.id: f for f in fields}
    
    # 构建依赖图
    graph = {}
    for f in fields:
        deps = set(f.dependencies.get("depends_on", []))
        # 只保留存在的依赖
        deps = deps.intersection(field_by_id.keys())
        graph[f.id] = deps
    
    # Kahn算法拓扑排序
    result = []
    remaining = dict(graph)
    
    while remaining:
        # 找出没有依赖的节点
        ready = [fid for fid, deps in remaining.items() if not deps]
        
        if not ready:
            # 检测到循环依赖
            raise ValueError(f"检测到循环依赖: {list(remaining.keys())}")
        
        # 添加到结果
        result.append([field_by_id[fid] for fid in ready])
        
        # 移除已处理节点
        for fid in ready:
            del remaining[fid]
        
        # 更新依赖
        for deps in remaining.values():
            deps -= set(ready)
    
    return result
