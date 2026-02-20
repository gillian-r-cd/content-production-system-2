// frontend/eslint.config.mjs
// 功能: ESLint Flat Config 入口（兼容 Next.js 16）
// 主要配置: eslint-config-next/core-web-vitals + eslint-config-next/typescript
// 数据结构: Flat config array

import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const config = [
  ...nextVitals,
  ...nextTs,
];

export default config;

