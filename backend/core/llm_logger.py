# backend/core/llm_logger.py
# 功能: LangChain 回调处理器，自动记录每次 LLM 调用到 GenerationLog
# 设计: 作为全局 callback 注入 LLM 实例，无需在每个调用点手动记录
# 关键: 这是调试日志记录的根本解决方案
# 数据结构:
#   prompt_input: JSON 数组，每项 {"role": str, "content": str, "tool_calls"?: list}
#   prompt_output: 完整的 LLM 输出文本（含 tool_calls JSON）

"""
LLM 调用日志回调

每次 LLM 调用（无论来自 agent_node、tool 内部还是其他场景）
都会自动创建一条 GenerationLog 记录，包含：
- 输入: 完整的 messages 数组（JSON 格式，不截断）
- 输出: 完整的 LLM 响应内容
- token 数（优先使用 API 返回值，否则估算）
- 耗时
- 成本
- 操作类型
"""

import json
import time
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

logger = logging.getLogger("llm_logger")


def _serialize_messages(messages: List[List[BaseMessage]]) -> str:
    """
    将 LangChain messages 序列化为 JSON 字符串，保留完整内容不截断。

    输出格式: JSON 数组，每项:
      {"role": "system"|"human"|"ai"|"tool", "content": "...", "tool_calls": [...]}

    设计原则:
    - 不截断任何内容 — 调试日志的意义就是完整记录
    - DB 字段为 Text 类型（SQLite 无长度限制），存储无问题
    - 前端负责展示层的折叠/滚动
    """
    result = []
    for msg_list in messages:
        for msg in msg_list:
            role = getattr(msg, "type", "unknown")
            content = getattr(msg, "content", "")

            entry: Dict[str, Any] = {"role": role}

            if isinstance(content, str):
                entry["content"] = content
            elif isinstance(content, list):
                # 多模态内容（如图片），尝试序列化
                entry["content"] = content
            else:
                entry["content"] = str(content)

            # 记录 tool_calls（AIMessage 的工具调用信息）
            tool_calls = getattr(msg, "tool_calls", None)
            if tool_calls:
                entry["tool_calls"] = [
                    {"name": tc.get("name", ""), "args": tc.get("args", {})}
                    for tc in tool_calls
                ]

            # 记录 tool_call_id（ToolMessage 的关联 ID）
            tool_call_id = getattr(msg, "tool_call_id", None)
            if tool_call_id:
                entry["tool_call_id"] = tool_call_id

            # 记录 name（ToolMessage 的工具名称）
            name = getattr(msg, "name", None)
            if name:
                entry["name"] = name

            result.append(entry)

    return json.dumps(result, ensure_ascii=False)


class GenerationLogCallback(AsyncCallbackHandler):
    """
    异步回调：每次 LLM 调用结束后写入 GenerationLog。
    
    使用方式：
        llm = get_chat_model(callbacks=[GenerationLogCallback(project_id="xxx")])
    或者在 ainvoke 时传入：
        llm.ainvoke(messages, config={"callbacks": [GenerationLogCallback(project_id="xxx")]})
    """

    def __init__(
        self,
        project_id: str = "",
        phase: str = "",
        operation: str = "",
        field_id: Optional[str] = None,
    ):
        super().__init__()
        self.project_id = project_id
        self.phase = phase
        self.operation = operation
        self.field_id = field_id
        self._start_times: Dict[UUID, float] = {}
        self._inputs: Dict[UUID, str] = {}

    async def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[BaseMessage]],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """LLM 调用开始时记录开始时间和完整输入（不截断）。"""
        self._start_times[run_id] = time.time()
        try:
            self._inputs[run_id] = _serialize_messages(messages)
        except Exception:
            self._inputs[run_id] = "(failed to serialize input)"

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """LLM 调用结束时创建 GenerationLog 记录（完整保存输入输出）。"""
        if not self.project_id:
            return

        start_time = self._start_times.pop(run_id, time.time())
        input_text = self._inputs.pop(run_id, "")
        duration_ms = int((time.time() - start_time) * 1000)

        try:
            # 提取输出（不截断）
            output_text = ""
            model_name = "unknown"
            tokens_in = 0
            tokens_out = 0

            if response.generations:
                gen = response.generations[0]
                if gen:
                    output_text = gen[0].text if gen[0].text else ""
                    # 尝试从 AIMessage 提取
                    if not output_text and hasattr(gen[0], "message"):
                        msg = gen[0].message
                        output_text = msg.content if hasattr(msg, "content") else ""
                    # 如果有 tool_calls，也记录到输出
                    if hasattr(gen[0], "message") and hasattr(gen[0].message, "tool_calls"):
                        tool_calls = gen[0].message.tool_calls
                        if tool_calls:
                            tc_json = json.dumps(
                                [{"name": tc.get("name", ""), "args": tc.get("args", {})}
                                 for tc in tool_calls],
                                ensure_ascii=False,
                            )
                            if output_text:
                                output_text += f"\n\n[tool_calls] {tc_json}"
                            else:
                                output_text = f"[tool_calls] {tc_json}"

            # 提取 token 使用量（如果 LLM 提供了）
            if response.llm_output:
                usage = response.llm_output.get("token_usage", {})
                tokens_in = usage.get("prompt_tokens", 0)
                tokens_out = usage.get("completion_tokens", 0)
                model_name = response.llm_output.get("model_name", "unknown")

            # 如果没有 token 信息，估算
            if not tokens_in:
                tokens_in = len(input_text) // 4
            if not tokens_out:
                tokens_out = len(output_text) // 4

            # 写入数据库（不截断 — Text 字段无长度限制）
            from core.database import get_db
            from core.models.generation_log import GenerationLog
            from core.models.base import generate_uuid

            db = next(get_db())
            try:
                gen_log = GenerationLog(
                    id=generate_uuid(),
                    project_id=self.project_id,
                    field_id=self.field_id,
                    phase=self.phase,
                    operation=self.operation or "llm_call",
                    model=model_name,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    duration_ms=duration_ms,
                    prompt_input=input_text,
                    prompt_output=output_text or "",
                    cost=GenerationLog.calculate_cost(model_name, tokens_in, tokens_out),
                    status="success",
                )
                db.add(gen_log)
                db.commit()
                logger.debug(
                    "[llm_logger] logged: op=%s, model=%s, in=%d, out=%d, %dms, input_len=%d, output_len=%d",
                    gen_log.operation, model_name, tokens_in, tokens_out, duration_ms,
                    len(input_text), len(output_text),
                )
            finally:
                db.close()

        except Exception as e:
            logger.warning("[llm_logger] failed to log GenerationLog: %s", e)
            # 清理残留的 start_times/inputs
            self._start_times.pop(run_id, None)
            self._inputs.pop(run_id, None)

    async def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """LLM 调用出错时也记录（status=failed）。"""
        if not self.project_id:
            self._start_times.pop(run_id, None)
            self._inputs.pop(run_id, None)
            return

        start_time = self._start_times.pop(run_id, time.time())
        input_text = self._inputs.pop(run_id, "")
        duration_ms = int((time.time() - start_time) * 1000)

        try:
            from core.database import get_db
            from core.models.generation_log import GenerationLog
            from core.models.base import generate_uuid

            db = next(get_db())
            try:
                gen_log = GenerationLog(
                    id=generate_uuid(),
                    project_id=self.project_id,
                    field_id=self.field_id,
                    phase=self.phase,
                    operation=self.operation or "llm_call",
                    model="unknown",
                    tokens_in=len(input_text) // 4,
                    tokens_out=0,
                    duration_ms=duration_ms,
                    prompt_input=input_text,
                    prompt_output="",
                    cost=0.0,
                    status="failed",
                    error_message=str(error)[:1000],
                )
                db.add(gen_log)
                db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.warning("[llm_logger] failed to log error: %s", e)
