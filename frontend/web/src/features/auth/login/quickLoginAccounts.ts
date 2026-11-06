/**
 * 登录页「一键登录」用的账号 —— **开发环境那两个** ✓。
 *
 * ⚠️ **两种角色都要给** ✓ —— **管理员只进管理台** ✓ (`roleRoutes` ✓:
 * 管理员登录后落到 `/admin/*` ✓), **用户侧那套页面** (工作台 / 对话 /
 * 任务 / 资源库…) **得用成员账号进** ✓ —— 只有一个管理员账号的话,
 * 开发环境**根本看不到用户侧长什么样** ✗✗.
 *
 * 密码与后端种子里的一致 (backend/composition/.../settings.py):
 *   QZDAP_DEV_ADMIN_PASSWORD / QZDAP_DEV_USER_PASSWORD
 */

export type QuickLoginRole = 'user' | 'admin';

export interface QuickLoginAccount {
  email: string;
  password: string;
  role: QuickLoginRole;
}

const DEV_ADMIN_EMAIL = 'admin@dev.qzdap.dev';
const DEV_ADMIN_PASSWORD = 'dev-admin-password-change-me';
const DEV_USER_EMAIL = 'user@dev.qzdap.dev';
const DEV_USER_PASSWORD = 'dev-user-password-change-me';

export function quickLoginAccounts(): QuickLoginAccount[] {
  return [
    { email: DEV_USER_EMAIL, password: DEV_USER_PASSWORD, role: 'user' },
    { email: DEV_ADMIN_EMAIL, password: DEV_ADMIN_PASSWORD, role: 'admin' },
  ];
}
