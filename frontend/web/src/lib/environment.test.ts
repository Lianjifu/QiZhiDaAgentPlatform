import { describe, expect, it } from 'vitest';
import { migrateLegacyStorageKeys, resolveRuntimeConfig, runtimeStorageKey } from './environment';

describe('runtime environment', () => {
  it('supports only the development business environment', () => {
    expect(resolveRuntimeConfig({ VITE_QZDAP_ENV: 'development' })).toEqual({
      environment: 'development',
    });
    expect(resolveRuntimeConfig({})).toEqual({ environment: 'development' });
  });

  it('rejects the retired demo / production / staging modes', () => {
    for (const env of ['demo', 'production', 'staging']) {
      expect(() => resolveRuntimeConfig({ VITE_QZDAP_ENV: env })).toThrow(
        '仅支持 development 环境',
      );
    }
  });

  it('ignores mock flags and always uses the real API', () => {
    const development = resolveRuntimeConfig({
      VITE_QZDAP_ENV: 'development',
      VITE_DATA_MODE: 'development-mock',
      VITE_USE_MOCK: 'true',
      VITE_USE_DEMO: 'true',
    });
    expect(development).toEqual({ environment: 'development' });
  });

  it('storage keys no longer carry the environment segment', () => {
    expect(runtimeStorageKey('token')).toBe('qzdap:token');
  });

  it('migrates the legacy environment-scoped keys once', () => {
    const store = new Map<string, string>([
      ['qzdap:development:development-api:token', 'tok'],
      ['qzdap:development:development-api:auth', '{"state":{}}'],
      ['qzdap:demo:demo:token', 'demo-tok'],
      ['qzdap:workspace', 'ws'],
    ]);
    const fake = {
      length: store.size,
      key: (i: number) => Array.from(store.keys())[i] ?? null,
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
    } as unknown as Storage;

    migrateLegacyStorageKeys(fake);

    expect(store.get('qzdap:token')).toBe('tok');
    expect(store.get('qzdap:auth')).toBe('{"state":{}}');
    expect(store.has('qzdap:development:development-api:token')).toBe(false);
    // 演示环境的 key 不搬 ✓
    expect(store.get('qzdap:demo:demo:token')).toBe('demo-tok');
    expect(store.get('qzdap:workspace')).toBe('ws');
  });
});
