/**
 * 运行时配置 —— **只剩开发环境** ✓（演示 / 预发 / 生产环境已退役 ✓）。
 *
 * 所以这里没有「要不要走 API」的开关 ✓ —— 数据永远走后端 ✓，
 * 也不需要第二套手写的数据源 ✓。
 */
export type AppEnvironment = 'development';

export interface RuntimeConfig {
  environment: AppEnvironment;
}

type EnvInput = Record<string, string | undefined>;

function readEnv(input?: EnvInput): EnvInput {
  if (input) return input;
  return import.meta.env as unknown as EnvInput;
}

export function resolveRuntimeConfig(input?: EnvInput): RuntimeConfig {
  const env = readEnv(input);
  const rawEnvironment = (env.VITE_QZDAP_ENV ?? '').trim().toLowerCase();
  if (rawEnvironment && rawEnvironment !== 'development') {
    throw new Error('企智搭仅支持 development 环境');
  }
  return { environment: 'development' };
}

/**
 * localStorage / react-query 的 key 前缀 —— 只剩一层 ✓。
 *
 * ⚠️ **老 key 带环境段** ✓（`qzdap:development:development-api:token` ✓）——
 * 删掉环境段后前缀变了 ✓ → 用 :func:`migrateLegacyStorageKeys` 搬一次 ✓
 * （否则用户会被登出 ✓）。
 */
export function runtimeStorageKey(name: string, _input?: EnvInput): string {
  return `qzdap:${name}`;
}

/** 老前缀 —— 只剩 development 那一套需要搬 ✓（demo 的 key 直接丢弃 ✓）。 */
const LEGACY_PREFIX = 'qzdap:development:development-api:';

/**
 * 把带环境段的旧 key 搬到新 key 下 ✓ —— 只搬 development 那套 ✓
 * （demo 的 key 不搬 ✓ —— 演示环境退役了 ✓）。
 *
 * ⚠️ **必须在应用挂载前跑** ✓ —— 否则 auth store 会先读到空 token ✓。
 */
export function migrateLegacyStorageKeys(storage: Storage | undefined = globalThis.localStorage): void {
  if (!storage) return;
  const stale: string[] = [];
  for (let i = 0; i < storage.length; i += 1) {
    const key = storage.key(i);
    if (!key || !key.startsWith(LEGACY_PREFIX)) continue;
    const name = key.slice(LEGACY_PREFIX.length);
    const next = `qzdap:${name}`;
    if (storage.getItem(next) === null) {
      storage.setItem(next, storage.getItem(key) ?? '');
    }
    stale.push(key);
  }
  stale.forEach((key) => storage.removeItem(key));
}
