// frontend/lib/backend-url.ts
// 功能: 统一解析前端与测试运行时使用的后端基础地址，兼容历史 BACKEND_URL 并收敛到 NEXT_PUBLIC_BACKEND_URL
// 主要导出: DEFAULT_BACKEND_URL, resolveBackendBaseUrl()
// 数据结构: BackendEnvSource（环境变量键值映射）

export const DEFAULT_BACKEND_URL = "http://localhost:8000";

export type BackendEnvSource = Record<string, string | undefined>;

function normalizeBackendBaseUrl(value: string): string {
  const trimmed = value.trim();
  const normalized = trimmed.replace(/\/+$/, "");
  return normalized || DEFAULT_BACKEND_URL;
}

export function resolveBackendBaseUrl(
  env: BackendEnvSource = process.env,
): string {
  return normalizeBackendBaseUrl(
    env.NEXT_PUBLIC_BACKEND_URL ||
      env.BACKEND_URL ||
      DEFAULT_BACKEND_URL,
  );
}
