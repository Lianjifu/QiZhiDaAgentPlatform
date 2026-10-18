/**
 * 登录会话 — 当前用户、Token、角色与权限。
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User, Permission, Role } from '@qzdap/web-types';
import { runtimeStorageKey } from '@/lib/environment';

const AUTH_STORAGE_KEY = runtimeStorageKey('auth');
const TOKEN_STORAGE_KEY = runtimeStorageKey('token');

/** 解析 JWT payload (不验签, 仅用于读取 exp 检查客户端过期). */
function decodeJwtPayload(token: string): { exp?: number } | null {
  const parts = token.split('.');
  if (parts.length !== 3) return null;
  try {
    const payload = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(payload));
  } catch {
    return null;
  }
}

/** JWT 是否已过期 (留 30s 缓冲避免边界). */
export function isTokenExpired(token: string, skewSeconds = 30): boolean {
  const payload = decodeJwtPayload(token);
  if (!payload?.exp) return true;
  return payload.exp - skewSeconds <= Math.floor(Date.now() / 1000);
}

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthed: boolean;
  login: (user: User, token: string) => void;
  logout: () => void;
  hasPermission: (p: Permission) => boolean;
  hasRole: (...roles: Role[]) => boolean;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      isAuthed: false,
      login: (user, token) => {
        localStorage.setItem(TOKEN_STORAGE_KEY, token);
        set({ user, token, isAuthed: true });
      },
      logout: () => {
        localStorage.removeItem(TOKEN_STORAGE_KEY);
        set({ user: null, token: null, isAuthed: false });
      },
      hasPermission: (p) => {
        const u = get().user;
        return !!u?.permissions.includes(p);
      },
      hasRole: (...roles) => {
        const r = get().user?.role;
        return !!r && roles.includes(r);
      },
    }),
    {
      name: AUTH_STORAGE_KEY,
      // Rehydrate 后把 zustand 持久化的 token 写回独立 localStorage key,
      // 让 ApiClient.getAuthToken() (在 main.tsx 注入, 直接读 localStorage)
      // 在页面刷新后能拿到 token. 否则 zustand state 有 token 但
      // localStorage[TOKEN_STORAGE_KEY] 是空的, 所有 /api/* 请求都 401.
      onRehydrateStorage: () => (state) => {
        if (state?.token) {
          // §8 Stage 8: 页面刷新后 token 可能已过期 (默认 TTL 1h, 跑过夜的话必过期).
          // 过期 token 会让 AuthMiddleware 401 → 整个 admin 页面 401.
          // 这里主动 logout, 把 user / token 全部清掉, 强制重登.
          if (isTokenExpired(state.token)) {
            localStorage.removeItem(TOKEN_STORAGE_KEY);
            // 触发 logout 同步 state (会清掉 persisted user)
            useAuthStore.setState({ user: null, token: null, isAuthed: false });
            // 关键: 也要清掉 zustand 自己的 persist storage, 否则下次 hydrate 又会
            // 读回 isAuthed=true 然后 useLogin 立即重定向到 /admin/overview → 全页 401.
            // 直接清 storage entry 而不是整个 clearStorage() (后者会清其它无关 key)
            try {
              const raw = localStorage.getItem(AUTH_STORAGE_KEY);
              if (raw) {
                const parsed = JSON.parse(raw);
                if (parsed?.state) {
                  parsed.state.user = null;
                  parsed.state.token = null;
                  parsed.state.isAuthed = false;
                  localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(parsed));
                }
              }
            } catch {
              // ignore — fallback: 下次 hydrate 仍会重复一次, 但不影响正确性
            }
            return;
          }
          localStorage.setItem(TOKEN_STORAGE_KEY, state.token);
        }
      },
    },
  ),
);
