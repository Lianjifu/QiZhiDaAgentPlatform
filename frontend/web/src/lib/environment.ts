export type AppEnvironment = 'demo' | 'development';
export type DataMode = 'demo' | 'development-api';

export interface RuntimeConfig {
  environment: AppEnvironment;
  dataMode: DataMode;
  apiEnabled: boolean;
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
    };
  }

  return {
    environment: 'development',
    dataMode: 'development-api',
    apiEnabled: true,
  };
}

export function runtimeStorageKey(name: string, input?: EnvInput): string {
  const config = resolveRuntimeConfig(input);
  return `qzdap:${config.environment}:${config.dataMode}:${name}`;
}
