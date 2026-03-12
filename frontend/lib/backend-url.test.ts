// frontend/lib/backend-url.test.ts
// 功能: 校验前端后端地址解析规则，防止 NEXT_PUBLIC_BACKEND_URL / BACKEND_URL / 默认端口再次漂移
// 主要测试: 解析优先级、历史变量兼容、默认值与尾部斜杠归一化
// 数据结构: Vitest describe/it 用例

import { describe, expect, it } from "vitest";

import { DEFAULT_BACKEND_URL, resolveBackendBaseUrl } from "./backend-url";

describe("resolveBackendBaseUrl", () => {
  it("prefers NEXT_PUBLIC_BACKEND_URL over BACKEND_URL", () => {
    expect(
      resolveBackendBaseUrl({
        NEXT_PUBLIC_BACKEND_URL: "http://localhost:8001/",
        BACKEND_URL: "http://localhost:8002",
      }),
    ).toBe("http://localhost:8001");
  });

  it("falls back to BACKEND_URL for legacy environments", () => {
    expect(
      resolveBackendBaseUrl({
        BACKEND_URL: "http://localhost:8010/",
      }),
    ).toBe("http://localhost:8010");
  });

  it("falls back to the default backend URL when env is missing", () => {
    expect(resolveBackendBaseUrl({})).toBe(DEFAULT_BACKEND_URL);
  });
});
