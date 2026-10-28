import { describe, expect, it, vi } from 'vitest';

const runtimeConfig = vi.hoisted(() =>
  vi.fn(() => ({ environment: 'development', dataMode: 'development-api' })),
);

vi.mock('@/lib/api-mode', () => ({
  runtimeConfig,
  apiBaseURL: () => '',
}));

import { quickLoginAccounts } from './quickLoginAccounts';

describe('quick-login accounts', () => {
  it('offers the dev account in development mode', () => {
    runtimeConfig.mockReturnValue({
      environment: 'development',
      dataMode: 'development-api',
    });
    const accounts = quickLoginAccounts();
    expect(accounts.map((a) => a.email)).toEqual(['admin@dev.qzdap.dev']);
    expect(accounts[0].password).toBe('dev-admin-password-change-me');
  });

  it('never offers demo accounts in development mode', () => {
    runtimeConfig.mockReturnValue({
      environment: 'development',
      dataMode: 'development-api',
    });
    expect(quickLoginAccounts().some((a) => a.email.endsWith('@acme.com'))).toBe(false);
  });

  it('offers the demo accounts in demo mode', () => {
    runtimeConfig.mockReturnValue({
      environment: 'demo',
      dataMode: 'demo',
    });
    const accounts = quickLoginAccounts();
    expect(accounts.map((a) => a.email)).toEqual(['user@acme.com', 'admin@acme.com']);
    // 两套密码不共用
    expect(accounts[0].password).toBe('demo-password-change-me');
    expect(accounts[0].password).not.toBe('dev-admin-password-change-me');
  });
});
