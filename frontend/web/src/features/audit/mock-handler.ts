/**
 * AdminToolAudit mock handler — 5 个 GET 端点;状态变更(收藏/解决/启停规则)在客户端完成。
 */
import {
  mockAuditEntries, mockAuditRisks, mockAuditRules, mockPermissionScopes,
} from './fixtures';

const withDelay = <T>(value: T, ms = 120) =>
  new Promise<T>((resolve) => setTimeout(() => resolve(value), ms));

export function wrapMockHandlerWithAdminAudit(fallback: (path: string, opts: any) => Promise<unknown> | unknown) {
  return async (path: string, opts: any = {}) => {
    const method = (opts?.method ?? 'GET').toUpperCase();
    if (method === 'POST' && path === '/api/admin/audit/rules') {
      const body = (opts.body ?? {}) as Record<string, string>;
      return withDelay({
        id: `rl-${Date.now()}`,
        name: body.name || '未命名规则',
        category: body.category || 'tool',
        condition: body.condition || '',
        action: body.action || 'log',
        severity: body.severity || 'medium',
        enabled: true,
        hitCount: 0,
        description: '由管理员手动创建',
      });
    }
    if (method !== 'GET') return fallback(path, opts);
    if (path === '/api/admin/audit/entries') return withDelay(mockAuditEntries);
    if (path === '/api/admin/audit/risks') return withDelay(mockAuditRisks);
    if (path === '/api/admin/audit/rules') return withDelay(mockAuditRules);
    if (path === '/api/admin/audit/scopes') return withDelay(mockPermissionScopes);
    return fallback(path, opts);
  };
}