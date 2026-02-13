# backend/core/llm_logger.py
# 功能: LangChain 回调处理器，自动记录每次 LLM 调用到 GenerationLog
# 设计: 作为全局 callback 注入 LLM 实例，无需在每个调用点手动记录
# 关键: 这是 P4（调试日志记录）的根本解决方案

"""
LLM 调用日志回调

每次 LLM 调用（无论来自 agent_node、tool 内部、cocreation 还是其他场景）
都会自动创建一条 GenerationLog 记录，包含：
- 输入/输出内容（截断到 2000 字）
- token 数（估算）
- 耗时
- 成本
- 操作类型（从 run_id 和 metadata 推断）
"""

import time
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

logger = logging.getLogger("llm_logger")


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
        """LLM 调用开始时记录开始时间和输入。"""
        self._start_times[run_id] = time.time()
        # 记录输入内容（截断）
        try:
            input_texts = []
            for msg_list in messages:
                for msg in msg_list:
                    role = getattr(msg, "type", "unknown")
                    content = getattr(msg, "content", "")
                    if isinstance(content, str):
                        input_texts.append(f"[{role}] {content[:300]}")
                    elif isinstance(content, list):
                        input_texts.append(f"[{role}] (structured content)")
            self._inputs[run_id] = "\n".join(input_texts)[:2000]
        except Exception:
            self._inputs[run_id] = "(failed to serialize input)"

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """LLM 调用结束时创建 GenerationLog 记录。"""
        if not self.project_id:
            return

        start_time = self._start_times.pop(run_id, time.time())
        input_text = self._inputs.pop(run_id, "")
        duration_ms = int((time.time() - start_time) * 1000)

        try:
            # 提取输出
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

            # 写入数据库
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
                    operation=self.operation or f"llm_call",
                    model=model_name,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    duration_ms=duration_ms,
                    prompt_input=input_text[:2000],
                    prompt_output=(output_text or "")[:2000],
                    cost=GenerationLog.calculate_cost(model_name, tokens_in, tokens_out),
                    status="success",
                )
                db.add(gen_log)
                db.commit()
                logger.debug(
                    "[llm_logger] logged: op=%s, model=%s, in=%d, out=%d, %dms",
                    gen_log.operation, model_name, tokens_in, tokens_out, duration_ms,
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
                    prompt_input=input_text[:2000],
                    prompt_output="",
                    cost=0.0,
                    status="failed",
                    error_message=str(error)[:500],
                )
                db.add(gen_log)
                db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.warning("[llm_logger] failed to log error: %s", e)
