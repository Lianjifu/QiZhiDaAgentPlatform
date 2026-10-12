/**
 * 管理侧「模型配置」mock handler — 接管 /api/admin/models/* 端点。
 * dev:demo 注入;prod 永不触达。
 */
import { mockModels, mockProviders, mockRoutes, mockHealth } from './fixtures';
import { ApiError } from '@qzdap/web-api';
import type {
  Model, Provider, RouteRule, HealthEvent,
  CreateModelVars, ProbeModelsVars, ConnectivityTestVars, CreateRouteVars, UpdateModelVars,
  ToggleRouteVars, DeleteModelVars, ToggleStarVars, BatchStatusVars,
} from './schema';

type MockOpts = { method?: string; body?: unknown; query?: Record<string, unknown> };

const state = {
  models: [...mockModels] as Model[],
  providers: [...mockProviders] as Provider[],
  routes: [...mockRoutes] as RouteRule[],
  health: [...mockHealth] as HealthEvent[],
  credentialIds: new Set<string>(),
  apiVersions: new Map<string, string | undefined>(),
};

function withDelay<T>(value: T, ms = 60): Promise<T> {
  return new Promise((resolve) => setTimeout(resolve, ms, value));
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
    if (!m) throw new ApiError('NOT_FOUND', '模型不存在', 404);
    const p = findProvider(m.providerId);
    return withDelay({ ...m, upstreamModel: m.upstreamModel ?? m.name, provider: {
      id: p?.id ?? m.providerId, name: p?.name ?? m.providerName, protocol: p?.protocol ?? 'openai', baseUrl: p?.baseUrl ?? '',
      apiKeyMasked: p?.apiKeyMasked ?? '', hasCredential: state.credentialIds.has(m.providerId), apiVersion: state.apiVersions.get(m.providerId),
    } });
  }

  if (method === 'POST' && path === '/api/admin/models/connectivity-test') {
    const v = (opts.body ?? {}) as ConnectivityTestVars;
    return withDelay({
      success: false,
      latencyMs: 0,
      statusCode: null,
      requestedModel: v.model ?? '',
      actualModel: null,
      response: null,
      error: '演示模式不支持真实供应商测试',
    });
  }

  if (method === 'POST' && path === '/api/admin/models/catalog') {
    const v = (opts.body ?? {}) as ProbeModelsVars;
    if (!v.apiKey?.trim() || !v.baseUrl?.trim()) {
      return withDelay(
        { models: [] as string[], error: '请填写 API Key 和请求地址后再拉取。' },
        180,
      );
    }
    return withDelay({ models: [], error: '演示模式不支持真实供应商目录', discoverySupported: false }, 220);
  }

  if (method === 'POST' && path === '/api/admin/models') {
    throw new ApiError('DEMO_UNSUPPORTED', '演示模式无法验证供应商模型，不支持新建接入。', 400);
  }

  if (method === 'PATCH' && detailMatch) {
    const v = (opts.body ?? {}) as UpdateModelVars;
    const target = state.models.find((x) => x.id === v.id);
    if (!target) throw new ApiError('NOT_FOUND', '模型不存在', 404);
    const currentProvider = findProvider(target.providerId);
    if ((v.patch.upstreamModel && v.patch.upstreamModel !== (target.upstreamModel ?? target.name)) || v.patch.provider?.apiKey ||
        (v.patch.provider && (v.patch.provider.baseUrl !== currentProvider?.baseUrl || v.patch.provider.protocol !== (currentProvider?.protocol ?? 'openai') || v.patch.provider.apiVersion !== state.apiVersions.get(target.providerId)))) {
      throw new ApiError('DEMO_UNSUPPORTED', '演示模式不支持真实供应商配置变更', 400);
    }
    const { provider, source: _source, verificationToken: _token, ...metadata } = v.patch;
    if (provider) {
      const p = findProvider(target.providerId);
      if (p) { p.name = provider.name; target.providerName = provider.name; }
    }
    Object.assign(target, metadata);
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
