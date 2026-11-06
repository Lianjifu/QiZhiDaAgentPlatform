/**
 * features/auth/login — 登录页。会话状态从 `@/features/auth` 取。
 *
 * 暴露:
 *  - LoginPage(默认导出) — App router lazy 引入
 *  - useLogin — 鉴权逻辑 hook
 *  - LoginBrandPanel / LoginCredentialsForm / LoginMfaStep / LoginQuickChips
 *    — 子组件供测试或他处复用
 */
export { default as LoginPage, default } from './LoginPage';
export { useLogin } from './useLogin';
export type {
  LoginStep,
  LoginMutationOutput,
  UseLoginOpts,
} from './useLogin';
export { LoginBrandPanel } from './LoginBrandPanel';
export type { LoginHeroBullet, LoginHeroStat } from './LoginBrandPanel';
export { LoginCredentialsForm } from './LoginCredentialsForm';
export { LoginMfaStep } from './LoginMfaStep';
export { LoginQuickChips } from './LoginQuickChips';
export type { LoginQuickRole } from './LoginQuickChips';