/**
 * useLogin — Login 鉴权逻辑单一所有者
 *
 * 集中 4 件事:
 *  1. 反向 redirect(已登录用户访问 /login → 跳走)
 *  2. IME guard(中文输入法回车不触发提交)
 *  3. `users/me` 回拉(adaptLogin 把 user 折成空串后,补一次真实用户信息)
 *  4. MFA step-2 骨架(URL `?step=mfa` 或 `_mfa@acme.com` 触发)
 *
 * Toast/i18n 副作用通过 opts.onXxx 回调抛给调用方(LoginPage),
 * 保持 hook 与 UI 文案解耦。
 */
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { useNavigate, useSearchParams, useLocation } from 'react-router-dom';
import { applyResponseAdapter } from '@qzdap/web-api';
import { useApiMutation, useApiQuery } from '@/services/query';
import { useAuthStore } from '@/features/auth';
import { resolvePostLoginRoute } from '@/features/auth/roleRoutes';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import type { User, Workspace } from '@qzdap/web-types';

export interface LoginMutationOutput {
  token: string;
  user: User;
  expiresAt?: string;
}

export type LoginStep = 'credentials' | 'mfa';

export interface UseLoginOpts {
  /** 登录成功、跳转前 */
  onAuthenticated?: (data: LoginMutationOutput) => void;
  /** 检测到 MFA 流程(URL 或邮箱 pattern) */
  onMfaRequired?: () => void;
  /** credentials 步骤空提交 */
  onEmptyCredentials?: () => void;
  /** MFA 步骤 code 格式错 */
  onInvalidMfa?: () => void;
  /** 真实后端错误 */
  onLoginError?: (message?: string) => void;
  /** MFA 暂未实现,占位提示 */
  onMfaSoon?: () => void;
}

const MFA_EMAIL_PATTERN = /_mfa@acme\.com$/i;
const MFA_CODE_PATTERN = /^\d{6}$/;

function readBuildVersion(): string {
  return ((import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env
    ?.VITE_BUILD_VERSION) ?? 'dev';
}

function identityServiceDown(err: unknown): boolean {
  if (!err || typeof err !== 'object') return false;
  const status = 'status' in err ? Number((err as { status?: number }).status) : NaN;
  const code = 'code' in err ? String((err as { code?: string }).code) : '';
  return status === 502 || status === 503 || status === 504 || status === 0
    || code === 'E_NETWORK' || code === 'E_BAD_RESPONSE' || code === 'E_TIMEOUT';
}

function sessionFromControlPlane(payload: unknown): LoginMutationOutput | null {
  if (!payload || typeof payload !== 'object') return null;
  const root = payload as Record<string, unknown>;
  const data = root.ok === true && root.data && typeof root.data === 'object'
    ? root.data as Record<string, unknown>
    : root;
  const token = typeof data.token === 'string' ? data.token : '';
  const user = data.user;
  if (!token || !user || typeof user !== 'object') return null;
  const record = user as User;
  if (!record.id || !record.email || !record.role) return null;
  return { token, user: record };
}

async function loginViaControlPlane(email: string, password: string): Promise<LoginMutationOutput> {
  const res = await fetch('/v1/identity/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  let json: unknown = null;
  try {
    json = await res.json();
  } catch {
    throw new Error('控制面登录响应无法解析');
  }
  if (!res.ok) {
    const message = json && typeof json === 'object' && 'message' in json
      ? String((json as { message?: string }).message || '')
      : '';
    throw new Error(message || '登录失败');
  }
  const adapted = applyResponseAdapter('POST', '/v1/identity/login', json);
  const session = sessionFromControlPlane(adapted);
  if (!session) throw new Error('登录响应缺少用户信息');
  return session;
}

function workspaceFromUser(user: User): Workspace | null {
  if (!user.workspaceId) return null;
  return {
    id: user.workspaceId,
    tenantId: user.tenantId,
    name: '当前工作空间',
    region: 'cn-east-1',
    plan: 'enterprise',
    memberCount: 1,
    complianceScore: 0,
    createdAt: new Date().toISOString(),
    ownerId: user.id,
    status: 'active',
  };
}

export function useLogin(opts: UseLoginOpts = {}) {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const authLogin = useAuthStore((s) => s.login);
  const isAuthed = useAuthStore((s) => s.isAuthed);
  const user = useAuthStore((s) => s.user);

  const initialStep: LoginStep = searchParams.get('step') === 'mfa' ? 'mfa' : 'credentials';

  const [step, setStep] = useState<LoginStep>(initialStep);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [mfa, setMfa] = useState('');

  const compositionRef = useRef(false);
  const compositionHandlers = useMemo(
    () => ({
      onCompositionStart: () => {
        compositionRef.current = true;
      },
      onCompositionEnd: () => {
        compositionRef.current = false;
      },
    }),
    [],
  );

  const meQuery = useApiQuery<User | null>(
    ['identity', 'me'],
    '/api/auth/me',
    undefined,
    { enabled: false, retry: false },
  );

  const enterWorkspace = useCallback((data: LoginMutationOutput) => {
    const looksLikeMfa =
      MFA_EMAIL_PATTERN.test(data?.user?.email ?? '') ||
      searchParams.get('step') === 'mfa';
    if (looksLikeMfa && !data?.user?.id) {
      setStep('mfa');
      opts.onMfaRequired?.();
      return;
    }
    authLogin(data.user, data.token);
    const workspace = workspaceFromUser(data.user);
    if (workspace) useWorkspaceStore.getState().setCurrent(workspace);
    opts.onAuthenticated?.(data);
    if (!data.user?.id) {
      const fetched = meQuery.data;
      if (fetched && (fetched.id || fetched.email)) {
        authLogin({ ...data.user, ...fetched }, data.token);
      } else {
        void meQuery
          .refetch()
          .then((me) => {
            if (me.data && (me.data.id || me.data.email)) {
              authLogin({ ...data.user, ...me.data }, data.token);
            }
          })
          .catch(() => {
            /* 身份服务未返回 profile 时保留登录结果 */
          });
      }
    }
    const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname;
    navigate(resolvePostLoginRoute(data.user.role, from), { replace: true });
  }, [authLogin, location.state, meQuery, navigate, opts, searchParams]);

  const mut = useApiMutation<LoginMutationOutput, { email: string; password: string }>(
    '/api/auth/login',
    {
      onSuccess: (data) => {
        enterWorkspace(data);
      },
      onError: (err: unknown, vars) => {
        const message =
          err && typeof err === 'object' && 'message' in err
            ? (err as { message?: string }).message
            : undefined;
        if (identityServiceDown(err) && vars?.email && vars?.password) {
          void loginViaControlPlane(vars.email, vars.password)
            .then((data) => enterWorkspace(data))
            .catch((fallbackErr: unknown) => {
              const fallbackMessage = fallbackErr instanceof Error ? fallbackErr.message : message;
              opts.onLoginError?.(fallbackMessage);
            });
          return;
        }
        opts.onLoginError?.(message);
      },
    },
  );

  useEffect(() => {
    if (!isAuthed) return;
    const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname;
    navigate(resolvePostLoginRoute(user?.role, from), { replace: true });
  }, [isAuthed, navigate, location.state, user?.role]);

  const submit = useCallback(
    (e?: FormEvent) => {
      e?.preventDefault();
      if (compositionRef.current) return;
      if (step === 'credentials') {
        if (!email || !password) {
          opts.onEmptyCredentials?.();
          return;
        }
        mut.mutate({ email, password });
      } else {
        if (!MFA_CODE_PATTERN.test(mfa)) {
          opts.onInvalidMfa?.();
          return;
        }
        opts.onMfaSoon?.();
      }
    },
    [step, email, password, mfa, mut, opts],
  );

  const chooseRole = useCallback((nextEmail: string) => {
    const nextPassword = 'dev-admin-password-change-me';
    setEmail(nextEmail);
    setPassword(nextPassword);
    setMfa('');
    mut.mutate({ email: nextEmail, password: nextPassword });
  }, [mut]);

  const goBack = useCallback(() => {
    setStep('credentials');
    setMfa('');
  }, []);

  return {
    step,
    setStep,
    goBack,
    email,
    setEmail,
    password,
    setPassword,
    mfa,
    setMfa,
    compositionHandlers,
    submit,
    isPending: mut.isPending,
    chooseRole,
    buildVersion: readBuildVersion(),
  };
}
