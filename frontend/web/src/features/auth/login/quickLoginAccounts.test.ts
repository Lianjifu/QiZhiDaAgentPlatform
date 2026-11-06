import { describe, expect, it } from 'vitest';

import { quickLoginAccounts } from './quickLoginAccounts';

describe('quick-login accounts', () => {
  it('offers both dev roles', () => {
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

  it('never offers the retired demo accounts', () => {
    expect(quickLoginAccounts().some((a) => a.email.endsWith('@acme.com'))).toBe(false);
  });
});
