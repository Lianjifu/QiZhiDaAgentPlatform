/**
 * 登录页「一键登录」用的账号 —— **按运行模式取**, 不混用.
 *
 * demo        → 演示库里的演示账号 (user@acme.com / admin@acme.com)
 * development → 开发库里的开发账号 (user@dev.qzdap.dev / admin@dev.qzdap.dev)
 *
 * 两套账号各属于各的库, 密码也不共用. 开发环境里不该出现演示账号 ——
 * 之前这里是写死的 acme.com, 于是开发环境也摆着两个演示角色.
 *
 * ⚠️ **两种角色都要给** ✓ —— **管理员只进管理台** ✓ (`roleRoutes` ✓:
 * 管理员登录后落到 `/admin/*` ✓), **用户侧那套页面** (工作台 / 对话 /
 * 任务 / 知识库…) **得用成员账号进** ✓ —— 只有一个管理员账号的话,
 * 开发环境**根本看不到用户侧长什么样** ✗✗.
 *
 * 密码与后端种子里的一致 (backend/composition/.../settings.py):
 *   QZDAP_DEMO_PASSWORD / QZDAP_DEV_ADMIN_PASSWORD / QZDAP_DEV_USER_PASSWORD
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
const DEV_USER_EMAIL = 'user@dev.qzdap.dev';
const DEV_USER_PASSWORD = 'dev-user-password-change-me';

export function quickLoginAccounts(): QuickLoginAccount[] {
  if (runtimeConfig().dataMode === 'demo') {
    return [
      { email: DEMO_USER_EMAIL, password: DEMO_PASSWORD, role: 'user' },
      { email: DEMO_ADMIN_EMAIL, password: DEMO_PASSWORD, role: 'admin' },
    ];
  }
  return [
    { email: DEV_USER_EMAIL, password: DEV_USER_PASSWORD, role: 'user' },
    { email: DEV_ADMIN_EMAIL, password: DEV_ADMIN_PASSWORD, role: 'admin' },
  ];
}
