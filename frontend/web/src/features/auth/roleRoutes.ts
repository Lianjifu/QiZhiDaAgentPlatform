import type { User } from '@qzdap/web-types';

export function defaultRouteForRole(role?: User['role']): string {
  if (role === 'admin') return '/admin/overview';
  if (role === 'auditor') return '/audit-center';
  return '/home';
}

/** 管理员只进控制台，成员只进工作台，避免登录后落到同一套页面。 */
export function pathAllowedForRole(pathname: string, role?: User['role']): boolean {
  if (!pathname || pathname === '/' || pathname.startsWith('/login')) return false;
  if (role === 'admin') return pathname.startsWith('/admin');
  if (role === 'auditor') {
    return pathname.startsWith('/audit-center') || pathname.startsWith('/admin/tool-audit');
  }
  return !pathname.startsWith('/admin');
}

export function resolvePostLoginRoute(role: User['role'] | undefined, from?: string): string {
  if (from && pathAllowedForRole(from, role)) return from;
  return defaultRouteForRole(role);
}
