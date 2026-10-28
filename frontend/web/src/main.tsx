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
import { runtimeStorageKey } from './lib/environment';
import { resolveWorkspaceHeader, ensureWorkspaceFromAuth } from './lib/workspace-header';

function installApiClient() {
  // 演示环境和开发环境**走同一套 API** —— 演示环境连的是 QZDAP_ENV=demo 的
  // 那个后端实例 (独立的演示库), 前端代码不因此分叉.
  //
  // 以前这里给演示环境注入了一份内存 mock, 于是演示数据和真实 API 是两份
  // 手写的数据, 必然越走越远 (实测: 后端 309 个端点, 演示数据只覆盖 4 个).
  // 现在演示数据由后端 demo 库提供 —— 契约天然对齐.
  // mock 只剩单测夹具的用途, 运行时不再注入.
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
