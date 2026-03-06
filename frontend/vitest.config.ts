// frontend/vitest.config.ts
// 功能: 前端 Vitest 配置，提供组件测试的 jsdom 环境与 tsconfig 路径解析
// 主要配置: test.environment / setupFiles / plugins
// 数据结构: Vitest UserConfig

import { defineConfig } from "vitest/config";
import tsconfigPaths from "vite-tsconfig-paths";

export default defineConfig({
  plugins: [tsconfigPaths()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
  },
});
