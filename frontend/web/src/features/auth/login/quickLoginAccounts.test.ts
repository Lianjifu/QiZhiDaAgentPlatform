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
  it('offers both dev roles in development mode', () => {
    runtimeConfig.mockReturnValue({
      environment: 'development',
      dataMode: 'development-api',
    });
    const accounts = quickLoginAccounts();
    // ⚠️ **用户侧也要有账号** ✓ —— 管理员只进管理台 ✓，用户侧那套页面
    // 得用成员账号进 ✓（没有它就只看得到管理台 ✗✗）。
    expect(accounts.map((a) => a.email)).toEqual([
      'user@dev.qzdap.dev',
      'admin@dev.qzdap.dev',
    ]);
    expect(accounts[0].password).toBe('dev-user-password-change-me');
    expect(accounts[1].password).toBe('dev-admin-password-change-me');
    // 两套口令不共用
    expect(accounts[0].password).not.toBe(accounts[1].password);
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
