import { describe, expect, it } from 'vitest';
import { resolveRuntimeConfig, runtimeStorageKey } from './environment';

describe('runtime environment', () => {
  it('supports only demo and development business environments', () => {
    expect(resolveRuntimeConfig({ VITE_QZDAP_ENV: 'demo' })).toMatchObject({
      environment: 'demo',
      dataMode: 'demo',
      apiEnabled: false,
    });
    expect(resolveRuntimeConfig({ VITE_QZDAP_ENV: 'development' })).toMatchObject({
      environment: 'development',
      dataMode: 'development-api',
      apiEnabled: true,
    });
  });

  it('rejects the removed production business mode', () => {
    expect(() => resolveRuntimeConfig({ VITE_QZDAP_ENV: 'production' })).toThrow(
      '仅支持 demo 或 development',
    );
  });

  it('ignores mock flags in development and always uses the real API', () => {
    const development = resolveRuntimeConfig({
      VITE_QZDAP_ENV: 'development',
      VITE_DATA_MODE: 'development-mock',
      VITE_USE_MOCK: 'true',
      VITE_USE_DEMO: 'true',
    });
    expect(development).toMatchObject({
      environment: 'development',
      dataMode: 'development-api',
      apiEnabled: true,
    });
    expect(runtimeStorageKey('auth', { VITE_QZDAP_ENV: 'demo' })).not.toBe(
      runtimeStorageKey('auth', { VITE_QZDAP_ENV: 'development' }),
    );
  });
});
