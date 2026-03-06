// frontend/playwright.config.ts
// 功能: 前端 Playwright 最小配置，专门承载自动拆分主链的浏览器级烟雾验证
// 主要配置: testDir / use.baseURL / trace
// 数据结构: PlaywrightTestConfig

import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:3000",
    trace: "retain-on-failure",
    headless: true,
  },
});
