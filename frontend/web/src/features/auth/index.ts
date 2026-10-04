/**
 * 登录业务入口。
 *
 * 会话状态从这里取。登录页在 `./login`，由路由单独引入，避免工作台打包进登录界面。
 */
export { useAuthStore } from './store';
export type { User, Permission, Role } from '@qzdap/web-types';
