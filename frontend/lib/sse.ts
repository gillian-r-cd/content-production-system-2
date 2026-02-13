// frontend/lib/sse.ts
// 功能: SSE (Server-Sent Events) 流式读取的唯一工具函数
// 主要函数: readSSEStream() — async generator，逐事件 yield 解析后的 JSON 对象
// 设计原则: 消除 ContentBlockEditor / ContentBlockCard / api.ts 等 5 处重复的 SSE 读取循环

/**
 * 从 fetch Response 中读取 SSE 流，逐事件 yield 解析后的 JSON 对象。
 *
 * 用法：
 * ```ts
 * const response = await blockAPI.generateStream(blockId, signal);
 * for await (const event of readSSEStream(response)) {
 *   if (event.chunk) accumulatedContent += event.chunk;
 *   if (event.done)  console.log("完成", event.content);
 *   if (event.error) throw new Error(event.error);
 * }
 * ```
 */
export async function* readSSEStream<T = Record<string, unknown>>(
  response: Response,
): AsyncGenerator<T> {
  const reader = response.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // 按换行切分，最后一段可能不完整 → 留到下次
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            yield JSON.parse(line.slice(6)) as T;
          } catch {
            // 忽略非 JSON 行（如 SSE 注释或不完整片段）
          }
        }
      }
    }

    // 处理最后残留的 buffer
    if (buffer.startsWith("data: ")) {
      try {
        yield JSON.parse(buffer.slice(6)) as T;
      } catch {
        // 忽略
      }
    }
  } finally {
    reader.releaseLock();
  }
}

