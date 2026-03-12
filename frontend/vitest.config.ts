// frontend/vitest.config.ts
// 功能: 前端 Vitest 配置，提供组件测试的 jsdom 环境、路径解析与测试范围约束
// 主要配置: test.environment / setupFiles / exclude / plugins
// 数据结构: Vitest UserConfig

import { configDefaults, defineConfig } from "vitest/config";
import tsconfigPaths from "vite-tsconfig-paths";

export default defineConfig({
  plugins: [tsconfigPaths()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    // Playwright 用例由 `npm run test:e2e` 执行，避免和 Vitest 混跑导致错误与内存膨胀。
    exclude: [...configDefaults.exclude, "e2e/**"],
    // 组件测试大量依赖 jsdom，并发过高会在本机触发 OOM，限制最大 worker 数保证全量回归可稳定执行。
    maxWorkers: 1,
  },
});
