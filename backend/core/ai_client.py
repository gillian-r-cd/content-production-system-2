# backend/core/ai_client.py
# 功能: AI客户端，封装OpenAI API调用，支持流式输出
# 主要类: AIClient
# 主要函数: chat(), stream_chat(), generate_structured()

"""
AI客户端
封装OpenAI API调用，支持:
1. 普通对话
2. 流式输出
3. 结构化输出
4. 自动记录日志
"""

import time
import json
from typing import AsyncGenerator, Optional, Any, Type, List, Tuple
from dataclasses import dataclass

from openai import OpenAI, AsyncOpenAI
from pydantic import BaseModel

from core.config import settings
from core.models import GenerationLog, generate_uuid


@dataclass
class ChatMessage:
    """聊天消息"""
    role: str  # system | user | assistant
    content: str


@dataclass
class ChatResponse:
    """聊天响应"""
    content: str
    model: str
    tokens_in: int
    tokens_out: int
    duration_ms: int
    cost: float


class AIClient:
    """
    AI客户端
    
    使用OpenAI API进行LLM调用
    支持同步和异步模式
    """
    
    def __init__(self):
        self.model = settings.openai_model or "gpt-5.1"
        
        # 同步客户端
        self._sync_client: Optional[OpenAI] = None
        # 异步客户端
        self._async_client: Optional[AsyncOpenAI] = None
    
    @property
    def sync_client(self) -> OpenAI:
        """获取同步客户端"""
        if self._sync_client is None:
            self._sync_client = OpenAI(
                api_key=settings.openai_api_key,
                organization=settings.openai_org_id or None,
                base_url=settings.openai_api_base or None,
                timeout=120.0,  # 增加超时时间到 120 秒
            )
        return self._sync_client
    
    @property
    def async_client(self) -> AsyncOpenAI:
        """获取异步客户端"""
        if self._async_client is None:
            self._async_client = AsyncOpenAI(
                api_key=settings.openai_api_key,
                organization=settings.openai_org_id or None,
                base_url=settings.openai_api_base or None,
                timeout=120.0,  # 增加超时时间到 120 秒
            )
        return self._async_client
    
    def chat(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> ChatResponse:
        """
        同步聊天
        
        Args:
            messages: 消息列表
            model: 模型名称（默认使用配置的模型）
            temperature: 温度
            max_tokens: 最大token数
        
        Returns:
            ChatResponse
        """
        model = model or self.model
        start_time = time.time()
        
        # 构建请求参数，排除None值
        kwargs = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
        }
        if max_tokens is not None:
            # gpt-4o / gpt-5.x 等新模型使用 max_completion_tokens
            kwargs["max_completion_tokens"] = max_tokens
        
        response = self.sync_client.chat.completions.create(**kwargs)
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        tokens_in = response.usage.prompt_tokens
        tokens_out = response.usage.completion_tokens
        cost = GenerationLog.calculate_cost(model, tokens_in, tokens_out)
        
        return ChatResponse(
            content=response.choices[0].message.content,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            duration_ms=duration_ms,
            cost=cost,
        )
    
    async def async_chat(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> ChatResponse:
        """
        异步聊天
        """
        model = model or self.model
        start_time = time.time()
        
        # 构建请求参数，排除None值
        kwargs = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
        }
        if max_tokens is not None:
            # gpt-4o / gpt-5.x 等新模型使用 max_completion_tokens
            kwargs["max_completion_tokens"] = max_tokens
        
        response = await self.async_client.chat.completions.create(**kwargs)
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        tokens_in = response.usage.prompt_tokens
        tokens_out = response.usage.completion_tokens
        cost = GenerationLog.calculate_cost(model, tokens_in, tokens_out)
        
        return ChatResponse(
            content=response.choices[0].message.content,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            duration_ms=duration_ms,
            cost=cost,
        )
    
    async def stream_chat(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """
        流式聊天
        
        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度
            max_tokens: 最大token数
        
        Yields:
            内容片段
        """
        model = model or self.model
        
        # 构建请求参数，排除None值
        kwargs = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens is not None:
            # gpt-4o / gpt-5.x 等新模型使用 max_completion_tokens
            kwargs["max_completion_tokens"] = max_tokens
        
        stream = await self.async_client.chat.completions.create(**kwargs)
        
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    
    async def generate_structured(
        self,
        messages: List[ChatMessage],
        response_model: Type[BaseModel],
        model: Optional[str] = None,
        temperature: float = 0.7,
    ) -> Tuple[BaseModel, ChatResponse]:
        """
        生成结构化输出
        
        使用OpenAI的JSON模式，并用Pydantic验证
        
        Args:
            messages: 消息列表
            response_model: Pydantic模型类
            model: 模型名称
            temperature: 温度
        
        Returns:
            (解析后的模型实例, ChatResponse)
        """
        model = model or self.model
        start_time = time.time()
        
        # 添加JSON格式要求到系统提示
        json_schema = response_model.model_json_schema()
        schema_prompt = f"\n\n请以JSON格式输出，遵循以下schema:\n```json\n{json.dumps(json_schema, ensure_ascii=False, indent=2)}\n```"
        
        # 修改最后一条消息或系统消息
        modified_messages = []
        for m in messages:
            if m.role == "system":
                modified_messages.append(ChatMessage(
                    role="system",
                    content=m.content + schema_prompt
                ))
            else:
                modified_messages.append(m)
        
        response = await self.async_client.chat.completions.create(
            model=model,
            messages=[{"role": m.role, "content": m.content} for m in modified_messages],
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        tokens_in = response.usage.prompt_tokens
        tokens_out = response.usage.completion_tokens
        cost = GenerationLog.calculate_cost(model, tokens_in, tokens_out)
        
        # 解析JSON
        content = response.choices[0].message.content
        parsed = response_model.model_validate_json(content)
        
        chat_response = ChatResponse(
            content=content,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            duration_ms=duration_ms,
            cost=cost,
        )
        
        return parsed, chat_response
    
    def create_log_entry(
        self,
        project_id: str,
        phase: str,
        operation: str,
        messages: List[ChatMessage],
        response: ChatResponse,
        field_id: Optional[str] = None,
        status: str = "success",
        error_message: str = "",
    ) -> GenerationLog:
        """
        创建生成日志条目
        
        Args:
            project_id: 项目ID
            phase: 阶段
            operation: 操作类型
            messages: 输入消息
            response: 响应
            field_id: 字段ID（可选）
            status: 状态
            error_message: 错误信息
        
        Returns:
            GenerationLog实例（未保存）
        """
        prompt_input = "\n\n---\n\n".join(
            f"[{m.role}]\n{m.content}" for m in messages
        )
        
        return GenerationLog(
            id=generate_uuid(),
            project_id=project_id,
            field_id=field_id,
            phase=phase,
            operation=operation,
            model=response.model,
            prompt_input=prompt_input,
            prompt_output=response.content,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            duration_ms=response.duration_ms,
            cost=response.cost,
            status=status,
            error_message=error_message,
        )


# 单例
ai_client = AIClient()

