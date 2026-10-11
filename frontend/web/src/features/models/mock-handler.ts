/**
 * 管理侧「模型配置」mock handler — 接管 /api/admin/models/* 端点。
 * dev:demo 注入;prod 永不触达。
 */
import { mockModels, mockProviders, mockRoutes, mockHealth } from './fixtures';
import { DEMO_PROVIDER_CATALOG } from './components/constants';
import type {
  Model, Provider, RouteRule, HealthEvent, ModelProtocol,
  CreateModelVars, ProbeModelsVars, CreateRouteVars, UpdateModelVars,
  ToggleRouteVars, DeleteModelVars, ToggleStarVars, BatchStatusVars,
} from './schema';

type MockOpts = { method?: string; body?: unknown; query?: Record<string, unknown> };

const state = {
  models: [...mockModels] as Model[],
  providers: [...mockProviders] as Provider[],
  routes: [...mockRoutes] as RouteRule[],
  health: [...mockHealth] as HealthEvent[],
};

function withDelay<T>(value: T, ms = 60): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

function uid(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
}

function findProvider(id: string): Provider | undefined {
  return state.providers.find((p) => p.id === id);
}

export async function adminModelsMockHandler(path: string, opts: MockOpts): Promise<unknown> {
  const method = (opts.method ?? 'GET').toUpperCase();

  if (method === 'GET' && path === '/api/admin/models') return withDelay(state.models.slice());
  if (method === 'GET' && path === '/api/admin/models/providers') return withDelay(state.providers.slice());
  if (method === 'GET' && path === '/api/admin/models/routes') return withDelay(state.routes.slice());
  if (method === 'GET' && path === '/api/admin/models/health') return withDelay(state.health.slice());

  const detailMatch = path.match(/^\/api\/admin\/models\/([^/]+)$/);
  if (method === 'GET' && detailMatch) {
    const m = state.models.find((x) => x.id === detailMatch[1]);
    return m ? withDelay(m) : withDelay({ error: 'not found' }, 200);
  }

  if (method === 'POST' && path === '/api/admin/models/catalog') {
    const v = (opts.body ?? {}) as ProbeModelsVars;
    if (!v.apiKey?.trim() || !v.baseUrl?.trim()) {
      return withDelay(
        { models: [] as string[], error: '请填写 API Key 和请求地址后再拉取。' },
        180,
      );
    }
    const protocol = (v.protocol ?? 'openai') as ModelProtocol;
    return withDelay({ models: [...(DEMO_PROVIDER_CATALOG[protocol] ?? [])] }, 220);
  }

  if (method === 'POST' && path === '/api/admin/models') {
    const v = (opts.body ?? {}) as CreateModelVars;
    const names = v.models.filter((n) => n.trim().length > 0);
    if (names.length === 0) return withDelay({ error: 'models required' }, 200);
    const providerId = uid('pv');
    const tail = v.apiKey.slice(-4);
    const provider: Provider = {
      id: providerId,
      name: v.providerName,
      region: 'custom',
      status: 'healthy',
      baseUrl: v.baseUrl,
      apiKeyMasked: tail ? `••••${tail}` : '••••',
      protocol: v.protocol,
      errorRate: 0,
      avgLatencyMs: 0,
      qps: 0,
    };
    state.providers.unshift(provider);
    let first: Model | null = null;
    for (const name of names) {
      const lower = name.toLowerCase();
      const task = lower.includes('embed') ? ['embedding' as const] : lower.includes('o1') || lower.includes('reason') ? ['reasoning' as const] : ['generation' as const];
      const created: Model = {
        id: uid('md'),
        name,
        providerId,
        providerName: v.providerName,
        task,
        contextWindow: 128000,
        priceIn: 0,
        priceOut: 0,
        latencyMs: 0,
        successRate: 0,
        status: 'draft',
        tier: 'balanced',
        starred: false,
        calls: 0,
        trend: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        description: `经 ${v.providerName}（${v.protocol}）接入`,
        tags: [v.protocol],
      };
      state.models.unshift(created);
      if (!first) first = created;
    }
    return withDelay(first);
  }

  if (method === 'PATCH' && detailMatch) {
    const v = (opts.body ?? {}) as UpdateModelVars;
    const target = state.models.find((x) => x.id === v.id);
    if (!target) return withDelay({ error: 'not found' }, 200);
    Object.assign(target, v.patch);
    return withDelay(target);
  }

  if (method === 'DELETE' && detailMatch) {
    const id = detailMatch[1];
    const idx = state.models.findIndex((x) => x.id === id);
    if (idx === -1) return withDelay({ error: 'not found' }, 200);
    state.models.splice(idx, 1);
    return withDelay({ id });
  }

  const starMatch = path.match(/^\/api\/admin\/models\/([^/]+)\/star$/);
  if (method === 'POST' && starMatch) {
    const id = starMatch[1];
    const v = (opts.body ?? {}) as ToggleStarVars;
    const target = state.models.find((x) => x.id === id);
    if (!target) return withDelay({ error: 'not found' }, 200);
    target.starred = v.starred;
    return withDelay(target);
  }

  if (method === 'POST' && path === '/api/admin/models/routes') {
    const v = (opts.body ?? {}) as CreateRouteVars;
    const created: RouteRule = {
      id: uid('rt'),
      name: v.name,
      task: v.task,
      strategy: v.strategy,
      priority: v.priority,
      primaryModelId: v.primaryModelId,
      fallbackModelIds: [],
      enabled: true,
      description: v.description,
    };
    state.routes.unshift(created);
    return withDelay(created);
  }

  const toggleRouteMatch = path.match(/^\/api\/admin\/models\/routes\/([^/]+)\/toggle$/);
  if (method === 'POST' && toggleRouteMatch) {
    const id = toggleRouteMatch[1];
    const v = (opts.body ?? {}) as ToggleRouteVars;
    void v;
    const target = state.routes.find((x) => x.id === id);
    if (!target) return withDelay({ error: 'not found' }, 200);
    target.enabled = !target.enabled;
    return withDelay(target);
  }

  const deleteRouteMatch = path.match(/^\/api\/admin\/models\/routes\/([^/]+)$/);
  if (method === 'DELETE' && deleteRouteMatch) {
    const id = deleteRouteMatch[1];
    const idx = state.routes.findIndex((x) => x.id === id);
    if (idx === -1) return withDelay({ error: 'not found' }, 200);
    state.routes.splice(idx, 1);
    return withDelay({ id });
  }

  if (method === 'POST' && path === '/api/admin/models/batch-status') {
    const v = (opts.body ?? {}) as BatchStatusVars;
    state.models.forEach((m) => {
      if (v.ids.includes(m.id)) m.status = v.status;
    });
    return withDelay({ ids: v.ids });
  }

  return undefined;
}

export function wrapMockHandlerWithAdminModels(fallback: (path: string, opts: any) => Promise<unknown>): (path: string, opts: any) => Promise<unknown> {
  return async (path, opts) => {
    const r = await adminModelsMockHandler(path, opts);
    return r === undefined ? fallback(path, opts) : r;
  };
}
