export type AppEnvironment = 'demo' | 'development';
export type DataMode = 'demo' | 'development-api' | 'development-mock';

export interface RuntimeConfig {
  environment: AppEnvironment;
  dataMode: DataMode;
  apiEnabled: boolean;
  queryFallbackEnabled: boolean;
}

type EnvInput = Record<string, string | undefined>;

function readEnv(input?: EnvInput): EnvInput {
  if (input) return input;
  return import.meta.env as unknown as EnvInput;
}

export function resolveRuntimeConfig(input?: EnvInput): RuntimeConfig {
  const env = readEnv(input);
  const rawEnvironment = (env.VITE_QZDAP_ENV ?? '').trim().toLowerCase();
  const isDemo = rawEnvironment === 'demo' || env.VITE_USE_DEMO === 'true';
  if (rawEnvironment && rawEnvironment !== 'demo' && rawEnvironment !== 'development') {
    throw new Error('企智搭仅支持 demo 或 development 环境');
  }

  if (isDemo) {
    return {
      environment: 'demo',
      dataMode: 'demo',
      apiEnabled: false,
      queryFallbackEnabled: false,
    };
  }

  const dataMode = env.VITE_DATA_MODE === 'development-mock' || env.VITE_USE_MOCK === 'true'
    ? 'development-mock'
    : 'development-api';
  return {
    environment: 'development',
    dataMode,
    apiEnabled: dataMode === 'development-api',
    queryFallbackEnabled: dataMode === 'development-api',
  };
}

export function runtimeStorageKey(name: string, input?: EnvInput): string {
  const config = resolveRuntimeConfig(input);
  return `qzdap:${config.environment}:${config.dataMode}:${name}`;
}

export function isQueryFallbackPolicy(policy: string | undefined): boolean {
  return policy === 'on-network-error' || policy === 'on-empty' || policy === 'on-network-error-or-empty';
}
