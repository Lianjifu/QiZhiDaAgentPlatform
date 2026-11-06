import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './app/App';
import { I18nProvider } from './i18n';
import './styles/global.css';
import './styles/hljs.css';
import { setApiClient, ApiClient } from '@qzdap/web-api';
import { useAuthStore, isTokenExpired } from './features/auth';
import { apiBaseURL } from './lib/api-mode';
import { migrateLegacyStorageKeys, runtimeStorageKey } from './lib/environment';
import { resolveWorkspaceHeader, ensureWorkspaceFromAuth } from './lib/workspace-header';

function installApiClient() {
  // 只剩开发环境一个 ✓（演示环境已退役 ✓）—— 前端永远走后端 API ✓，
  // 运行时**不注入任何 mock** ✓（mock 只剩单测夹具的用途 ✓）。
  setApiClient(
    new ApiClient(
      apiBaseURL(),
      () => {
        const t = localStorage.getItem(runtimeStorageKey('token'));
        if (!t) return null;
        if (isTokenExpired(t)) {
          // 过期 token 主动清理, 让 useAuthStore 同步登出
          localStorage.removeItem(runtimeStorageKey('token'));
          useAuthStore.getState().logout();
          return null;
        }
        return t;
      },
      undefined, // 运行时不再注入 mock —— 见上面的说明
      () => {
        const user = useAuthStore.getState().user;
        const base: Record<string, string> = {
          'x-workspace-id': resolveWorkspaceHeader(),
        };
        if (!user) return base;
        return {
          ...base,
          'x-tenant-id': user.tenantId,
          'x-user-id': user.id,
        };
      },
      // 仅当 401 来自身份相关端点时,才视为会话失效并退出登录;
      // 其他端点的 401 不应当场抹掉 token — 由各页面处理
      (request: { path: string; status: number }) => {
        const lower = request.path.toLowerCase();
        const isAuthEndpoint =
          lower.includes('/auth/login') ||
          lower.includes('/auth/me') ||
          lower.includes('/identity/login') ||
          lower.includes('/identity/users/me') ||
          lower.includes('/identity/refresh');
        if (!isAuthEndpoint) return;
        useAuthStore.getState().logout();
        if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
          window.location.assign('/login');
        }
      },
      // uid-注入型路径(/api/api-keys 等):从 auth store 拿当前用户 id
      () => useAuthStore.getState().user?.id ?? null,
    ),
  );
}

// ⚠️ **搬旧 key 必须在 auth store 读之前** ✓ —— 老 key 带环境段
// (``qzdap:development:development-api:token`` ✓），新 key 少一层 ✓
// —— 不搬的话用户会被登出 ✓。
migrateLegacyStorageKeys();

installApiClient();

// 同步 workspaceId: 刷新后 workspaceStore 是空的, 用 user.workspaceId 兜底
// (api-client getContextHeaders 依赖 workspaceStore.currentWorkspaceId, 没有就会 422)
ensureWorkspaceFromAuth();
useAuthStore.persist.onFinishHydration(() => ensureWorkspaceFromAuth());

if (import.meta.hot) {
  import.meta.hot.accept('./lib/api-mode', () => {
    installApiClient();
  });
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <I18nProvider>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </I18nProvider>
  </React.StrictMode>,
);
