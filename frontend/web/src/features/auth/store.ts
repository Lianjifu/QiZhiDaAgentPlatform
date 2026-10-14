/**
 * 登录会话 — 当前用户、Token、角色与权限。
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User, Permission, Role } from '@qzdap/web-types';
import { runtimeStorageKey } from '@/lib/environment';

const AUTH_STORAGE_KEY = runtimeStorageKey('auth');
const TOKEN_STORAGE_KEY = runtimeStorageKey('token');

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
    { name: AUTH_STORAGE_KEY },
  ),
);
