/**
 * 后端响应 → 前端约定的形状适配器。
 *
 * 适配分两层:
 * 1. **Per-path 适配** — 已知形状缺口(如 login)在这里写专门分支
 * 2. **通用 snake_case → camelCase** — 所有响应过一遍 camelizeKeys,
 *    避免每条路径单独写 adapter
 */
import type { HttpMethod } from './pathMap';
import { camelizeKeys } from './camelizeKeys';

type AnyRecord = Record<string, unknown>;

/**
 * 把后端 `{access_token, expires_at, user}` 折成前端 `Login.tsx` 期望的
 * `{token, user, expiresAt}`。
 *
 * 后端 `LoginResponse.user` 自 2026-09 起包含真实 id/email/tenant_id/
 * display_name，前端不再需要二次 `GET /v1/identity/users/me` 拉取。
 *
 * 旧契约(只返回 token)的兜底分支保留：user.id/email/tenantId/name 留空，
 * 调用方按需决定是否二次拉取(目前 useAuthStore 会合并 users/me 兜底)。
 */
export interface LoginAdapterOutput {
  token: string;
  user: {
    id: string;
    email: string;
    role: string;
    tenantId: string;
    name: string;
    permissions: string[];
  };
  expiresAt: string;
}

function adaptLogin(rawData: unknown): LoginAdapterOutput | unknown {
  if (!rawData || typeof rawData !== 'object') return rawData;
  const r = rawData as AnyRecord;
  // 后端字段：access_token, expires_at；宽松接受 camelCase 也行
  const tokenRaw = r.access_token ?? r.accessToken;
  const expiresRaw = r.expires_at ?? r.expiresAt;
  if (typeof tokenRaw !== 'string') return rawData;
  // 新契约: 后端在 login 响应里直接返回 user 对象
  const u = (r.user ?? {}) as AnyRecord;
  const userId = typeof u.id === 'string' ? u.id : '';
  const userEmail = typeof u.email === 'string' ? u.email : '';
  const tenantId = typeof u.tenant_id === 'string' ? u.tenant_id : typeof u.tenantId === 'string' ? u.tenantId : '';
  const displayName = typeof u.display_name === 'string' ? u.display_name : typeof u.name === 'string' ? u.name : '';
  const explicitRole = typeof u.role === 'string' ? u.role : '';
  const emailKey = userEmail.toLowerCase();
  const role = explicitRole === 'admin' || explicitRole === 'auditor' || explicitRole === 'user'
    ? explicitRole
    : emailKey.startsWith('admin@')
      ? 'admin'
      : emailKey.startsWith('audit@')
        ? 'auditor'
        : 'user';
  const workspaceId = typeof u.workspace_id === 'string'
    ? u.workspace_id
    : typeof u.workspaceId === 'string' ? u.workspaceId : '';
  const permissions = Array.isArray(u.permissions) ? u.permissions.filter((item): item is string => typeof item === 'string') : [];
  return {
    token: tokenRaw,
    user: {
      id: userId,
      email: userEmail,
      role,
      tenantId,
      name: displayName,
      permissions,
      workspaceId,
      workspaceIds: workspaceId ? [workspaceId] : [],
      environmentScopes: [],
      mfaEnabled: false,
    },
    expiresAt: typeof expiresRaw === 'string' ? expiresRaw : (typeof expiresRaw === 'number' ? String(expiresRaw) : ''),
  };
}

const PASSTHROUGH = (raw: unknown): unknown => raw;
void PASSTHROUGH;

/**
 * 把后端 `qzdap_kernel` 错误码映射到前端 `E_*` 编码空间。
 *
 * 后端 errors.py 的稳定码是 plain UPPER_SNAKE (`AUTHENTICATION_FAILED`,
 * `FORBIDDEN`, `NOT_FOUND`, ...); 前端约定使用 `E_AUTH_FAILED`,
 * `E_FORBIDDEN`, ... 等 `E_*` 编码(便于日志聚合 + 与 mock 模式一致)。
 *
 * 未知 code 原样返回 —— 保留运维诊断信息,不静默改写。
 */
const BACKEND_ERROR_TO_FRONTEND: Record<string, string> = {
  VALIDATION_ERROR: 'E_BAD_REQUEST',
  AUTHENTICATION_FAILED: 'E_AUTH_FAILED',
  INVALID_CREDENTIALS: 'E_AUTH_FAILED',
  FORBIDDEN: 'E_FORBIDDEN',
  ACTION_DENIED: 'E_FORBIDDEN',
  APPROVAL_REQUIRED: 'E_APPROVAL_REQUIRED',
  NOT_FOUND: 'E_NOT_FOUND',
  CONFLICT: 'E_CONFLICT',
  BUSINESS_RULE_VIOLATED: 'E_BUSINESS_RULE',
  RATE_LIMITED: 'E_RATE_LIMITED',
  EXTERNAL_SERVICE_ERROR: 'E_UPSTREAM',
  INTERNAL_ERROR: 'E_INTERNAL',
};

export function adaptErrorCode(backendCode: string): string {
  if (!backendCode) return 'E_UNKNOWN';
  if (backendCode.startsWith('E_')) return backendCode;
  return BACKEND_ERROR_TO_FRONTEND[backendCode] ?? backendCode;
}

/**
 * 按 (method, path) 选 adapter。
 * `path` 应当是已 translate 过的后端路径,方便统一匹配。
 */
export function applyResponseAdapter(
  method: HttpMethod,
  path: string,
  rawData: unknown,
): unknown {
  let adapted: unknown = rawData;
  // Per-path 适配(数量少且形状特殊的端点)
  if (method === 'POST' && path === '/v1/identity/login') {
    adapted = adaptLogin(rawData);
  }
  // 通用 snake_case → camelCase,适配后的对象再递归改 key
  // (login adapter 已经是 camelCase 形状,这里 idempotent)
  return camelizeKeys(adapted);
}