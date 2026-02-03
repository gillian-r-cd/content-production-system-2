// frontend/next.config.js
// 功能: Next.js配置

/** @type {import('next').NextConfig} */
const nextConfig = {
  // 环境变量
  env: {
    BACKEND_URL: process.env.BACKEND_URL || "http://localhost:8000",
  },
};

module.exports = nextConfig;

