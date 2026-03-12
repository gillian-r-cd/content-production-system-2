// frontend/next.config.js
// 功能: Next.js 配置，统一向浏览器端暴露后端基础地址
// 主要配置: NEXT_PUBLIC_BACKEND_URL / BACKEND_URL
// 数据结构: nextConfig

/** @type {import('next').NextConfig} */
const DEFAULT_BACKEND_URL = "http://localhost:8000";
const backendUrl = (
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  process.env.BACKEND_URL ||
  DEFAULT_BACKEND_URL
).trim() || DEFAULT_BACKEND_URL;

const nextConfig = {
  env: {
    NEXT_PUBLIC_BACKEND_URL: backendUrl,
    BACKEND_URL: backendUrl,
  },
};

module.exports = nextConfig;

