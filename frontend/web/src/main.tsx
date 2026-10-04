import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './app/App';
import { I18nProvider } from './i18n';
import './styles/global.css';
import { setApiClient, ApiClient, mockHandlerWithAdapters } from '@qzdap/web-api';
import { useAuthStore } from './features/auth';
import { apiBaseURL, isDemoApiMode } from './lib/api-mode';
import { resolveWorkspaceHeader } from './lib/workspace-header';
import { wrapMockHandlerWithCatalog } from './features/user/catalog';
import { wrapMockHandlerWithSkills } from './features/user/skills/mock-handler';
import { wrapMockHandlerWithAutomations } from './features/user/automations/mock-handler';
import { wrapMockHandlerWithTeam } from './features/user/team/mock-handler';
import { wrapMockHandlerWithUserKnowledge } from './features/user/knowledge/mock-handler';
import { wrapMockHandlerWithAdminNotifications } from './features/notifications/mock-handler';
import { wrapMockHandlerWithAdminKnowledge } from './features/knowledge/mock-handler';
import { wrapMockHandlerWithAdminQuotas } from './features/quotas/mock-handler';
import { wrapMockHandlerWithAdminModels } from './features/models/mock-handler';
import { wrapMockHandlerWithAdminAgents } from './features/agents/mock-handler';
import { wrapMockHandlerWithAdminSkills } from './features/skills/mock-handler';
import { wrapMockHandlerWithAdminOverview } from './features/overview/mock-handler';
import { wrapMockHandlerWithAdminOperations } from './features/operations/mock-handler';
import { wrapMockHandlerWithAdminAudit } from './features/audit/mock-handler';
import { wrapMockHandlerWithAdminMetrics } from './features/metrics/mock-handler';
import { wrapMockHandlerWithAdminMemory } from './features/memory/mock-handler';
import { wrapMockHandlerWithAdminWorkflows } from './features/workflows/mock-handler';
import { wrapMockHandlerWithAdminEvaluations } from './features/evaluations/mock-handler';
import { wrapMockHandlerWithAdminRegressions } from './features/regressions/mock-handler';
import { wrapMockHandlerWithAdminFeedback } from './features/feedback/mock-handler';

function installApiClient() {
  // 默认真实 API；仅演示模式注入本地 Handler。
  // Catalog 投影需在最外层，优先于旧用户 mock，读取内层 admin store。
  const demoMode = isDemoApiMode();
  const mockHandler = demoMode
    ? wrapMockHandlerWithCatalog(
        wrapMockHandlerWithSkills(
          wrapMockHandlerWithAutomations(
            wrapMockHandlerWithTeam(
              wrapMockHandlerWithUserKnowledge(
                wrapMockHandlerWithAdminKnowledge(
                  wrapMockHandlerWithAdminNotifications(
                    wrapMockHandlerWithAdminQuotas(
                      wrapMockHandlerWithAdminModels(
                        wrapMockHandlerWithAdminAgents(
                          wrapMockHandlerWithAdminSkills(
                            wrapMockHandlerWithAdminOverview(
                              wrapMockHandlerWithAdminOperations(
                                wrapMockHandlerWithAdminAudit(
                                  wrapMockHandlerWithAdminMetrics(
                                    wrapMockHandlerWithAdminMemory(
                                      wrapMockHandlerWithAdminWorkflows(
                                        wrapMockHandlerWithAdminEvaluations(
                                          wrapMockHandlerWithAdminRegressions(
                                            wrapMockHandlerWithAdminFeedback(mockHandlerWithAdapters),
                                          ),
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      )
    : undefined;
  setApiClient(
    new ApiClient(
      apiBaseURL(),
      () => localStorage.getItem('token'),
      mockHandler,
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
          ...(demoMode ? {
            'x-mock-role': user.role,
            'x-mock-actor': user.name,
            'x-mock-user-id': user.id,
            'x-mock-permissions': user.permissions.join(','),
          } : {}),
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
