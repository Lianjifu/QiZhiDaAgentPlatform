export type AppEnvironment = 'demo' | 'development';
export type DataMode = 'demo' | 'development-api';

/**
 * 运行时配置 —— demo 和 development 走**同一套前端代码 + 同一个 API 协议**,
 * 区别只在后端连的是哪个实例 (演示实例 / 开发实例) 和哪个库.
 *
 * 所以这里没有 "要不要走 API" 的开关: 演示数据天然与真实 API 对齐,
 * 不需要 (也没有) 第二份手写的数据源.
 */
export interface RuntimeConfig {
  environment: AppEnvironment;
  dataMode: DataMode;
}

type EnvInput = Record<string, string | undefined>;

function readEnv(input?: EnvInput): EnvInput {
  if (input) return input;
  return import.meta.env as unknown as EnvInput;
}

export function resolveRuntimeConfig(input?: EnvInput): RuntimeConfig {
  const env = readEnv(input);
  const rawEnvironment = (env.VITE_QZDAP_ENV ?? '').trim().toLowerCase();
  if (rawEnvironment && rawEnvironment !== 'demo' && rawEnvironment !== 'development') {
    throw new Error('企智搭仅支持 demo 或 development 环境');
  }

  // 未显式配置时按 development 处理 —— 演示环境必须靠 VITE_QZDAP_ENV=demo
  // 显式打开, 不能靠某个"顺手就生效"的旁路开关.
  if (rawEnvironment === 'demo') {
    return {
      environment: 'demo',
      dataMode: 'demo',
    };
  }

  return {
    environment: 'development',
    dataMode: 'development-api',
  };
}

export function runtimeStorageKey(name: string, input?: EnvInput): string {
  const config = resolveRuntimeConfig(input);
  return `qzdap:${config.environment}:${config.dataMode}:${name}`;
}
