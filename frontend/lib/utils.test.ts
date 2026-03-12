// frontend/lib/utils.test.ts
// 功能: 覆盖通知参数解析兼容层，防止旧调用方式把 success/error 当成正文显示
// 主要测试: resolveNotificationArgs

import { describe, expect, it, vi } from "vitest";

import { resolveNotificationArgs } from "./utils";

describe("resolveNotificationArgs", () => {
  it("treats a legacy tone-only second argument as the notification tone", () => {
    expect(resolveNotificationArgs("success")).toEqual({
      body: "",
      tone: "success",
      onClick: undefined,
    });
  });

  it("preserves explicit body text and trailing tone", () => {
    expect(resolveNotificationArgs("同步已完成", "success")).toEqual({
      body: "同步已完成",
      tone: "success",
      onClick: undefined,
    });
  });

  it("accepts an onClick handler without confusing it for body text", () => {
    const onClick = vi.fn();

    expect(resolveNotificationArgs("warning", onClick)).toEqual({
      body: "",
      tone: "warning",
      onClick,
    });
  });
});
