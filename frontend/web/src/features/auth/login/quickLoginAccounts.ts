/**
 * 登录页「一键登录」用的账号 —— **按运行模式取**, 不混用.
 *
 * demo        → 演示库里的演示账号 (admin@acme.com / user@acme.com)
 * development → 开发库里的开发账号 (admin@dev.qzdap.dev)
 *
 * 两套账号各属于各的库, 密码也不共用. 开发环境里不该出现演示账号 ——
 * 之前这里是写死的 acme.com, 于是开发环境也摆着两个演示角色.
 *
 * 密码与后端种子里的一致 (backend/composition/.../settings.py):
 *   QZDAP_DEMO_PASSWORD / QZDAP_DEV_ADMIN_PASSWORD
 */
import { runtimeConfig } from '@/lib/api-mode';

export type QuickLoginRole = 'user' | 'admin';

export interface QuickLoginAccount {
  email: string;
  password: string;
  role: QuickLoginRole;
}

const DEMO_ADMIN_EMAIL = 'admin@acme.com';
const DEMO_USER_EMAIL = 'user@acme.com';
const DEMO_PASSWORD = 'demo-password-change-me';

const DEV_ADMIN_EMAIL = 'admin@dev.qzdap.dev';
const DEV_ADMIN_PASSWORD = 'dev-admin-password-change-me';

export function quickLoginAccounts(): QuickLoginAccount[] {
  if (runtimeConfig().dataMode === 'demo') {
    return [
      { email: DEMO_USER_EMAIL, password: DEMO_PASSWORD, role: 'user' },
      { email: DEMO_ADMIN_EMAIL, password: DEMO_PASSWORD, role: 'admin' },
    ];
  }
  return [{ email: DEV_ADMIN_EMAIL, password: DEV_ADMIN_PASSWORD, role: 'admin' }];
}
