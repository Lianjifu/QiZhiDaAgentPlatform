import { resolveRuntimeConfig, type RuntimeConfig } from './environment';

export function isDemoApiMode(): boolean {
  return resolveRuntimeConfig().environment === 'demo';
}

export function runtimeConfig(): RuntimeConfig {
  return resolveRuntimeConfig();
}

function isLoopbackBase(url: string): boolean {
  try {
    const host = new URL(url).hostname;
    return host === '127.0.0.1' || host === 'localhost' || host === '::1';
  } catch {
    return false;
  }
}

/**
 * 开发态默认走同源 `/api`（Vite proxy → qzdap-gateway :9150），避免浏览器/Cursor 沙箱
 * 无法直连环回地址导致控制面读取失败。
 * 需要直连时设置 `VITE_API_DIRECT=true` 并填写非空 `VITE_API_BASE`。
 */
export function apiBaseURL(): string {
  if (!resolveRuntimeConfig().apiEnabled) return '';
  const raw = (import.meta.env.VITE_API_BASE as string | undefined)?.trim();
  const forceDirect = import.meta.env.VITE_API_DIRECT === 'true';

  if (import.meta.env.DEV && !forceDirect) {
    if (!raw || isLoopbackBase(raw)) return '';
  }
  if (!raw) return '';
  return raw.replace(/\/$/, '');
}
