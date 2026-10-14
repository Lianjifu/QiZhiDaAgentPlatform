/**
 * Sanity check — admin-models-mock-handler returns fixtures for each list
 * endpoint; create / patch / delete round-trip through in-memory state.
 */
import { describe, expect, it } from 'vitest';
import { wrapMockHandlerWithAdminModels } from '@/features/models/mock-handler';

describe('admin-models-mock-handler', () => {
  it('returns list endpoints with seed counts', async () => {
    const wrap = wrapMockHandlerWithAdminModels(async () => undefined);
    expect((await wrap('/api/admin/models', { method: 'GET' })) as unknown[]).toHaveLength(9);
    expect((await wrap('/api/admin/models/providers', { method: 'GET' })) as unknown[]).toHaveLength(5);
    expect((await wrap('/api/admin/models/routes', { method: 'GET' })) as unknown[]).toHaveLength(6);
    expect((await wrap('/api/admin/models/health', { method: 'GET' })) as unknown[]).toHaveLength(4);
  });

  it('refuses unverified model creation but allows demo route creation', async () => {
    const wrap = wrapMockHandlerWithAdminModels(async () => undefined);
    await expect(wrap('/api/admin/models', { method: 'POST', body: { providerName: '测试', apiKey: 'sk-test', baseUrl: 'https://api.openai.com/v1', protocol: 'openai', models: ['gpt-4o'] } })).rejects.toThrow('演示模式无法验证供应商模型');

    const createdRoute = (await wrap('/api/admin/models/routes', {
      method: 'POST',
      body: { name: '新路由', task: 'reasoning', strategy: 'quality-first', priority: 50, primaryModelId: 'md-gpt4o', description: 'test' },
    })) as { id: string; enabled: boolean };
    expect(createdRoute.enabled).toBe(true);
  });

  it('never fabricates supplier catalogs', async () => {
    const wrap = wrapMockHandlerWithAdminModels(async () => undefined);
    const openai = (await wrap('/api/admin/models/catalog', {
      method: 'POST',
      body: { apiKey: 'sk-test', baseUrl: 'https://api.openai.com/v1', protocol: 'openai' },
    })) as { models: string[] };
    expect(openai.models).toEqual([]);
    const claude = (await wrap('/api/admin/models/catalog', {
      method: 'POST',
      body: { apiKey: 'sk-test', baseUrl: 'https://api.anthropic.com', protocol: 'anthropic' },
    })) as { models: string[] };
    expect(claude.models).toEqual([]);
  });

  it('toggles a route and patches a model', async () => {
    const wrap = wrapMockHandlerWithAdminModels(async () => undefined);
    const beforeRoutes = (await wrap('/api/admin/models/routes', { method: 'GET' })) as Array<{ id: string; enabled: boolean }>;
    const enabledBefore = beforeRoutes[0].enabled;
    const toggled = (await wrap(`/api/admin/models/routes/${beforeRoutes[0].id}/toggle`, { method: 'POST', body: { id: beforeRoutes[0].id } })) as { enabled: boolean };
    expect(toggled.enabled).toBe(!enabledBefore);

    const beforeModels = (await wrap('/api/admin/models', { method: 'GET' })) as Array<{ id: string; starred: boolean; name: string }>;
    const newStarred = !beforeModels[0].starred;
    const starMatch = (await wrap(`/api/admin/models/${beforeModels[0].id}/star`, { method: 'POST', body: { id: beforeModels[0].id, starred: newStarred } })) as { starred: boolean; name: string };
    expect(starMatch.starred).toBe(newStarred);
  });

  it('batch sets status and deletes a model', async () => {
    const wrap = wrapMockHandlerWithAdminModels(async () => undefined);
    const before = (await wrap('/api/admin/models', { method: 'GET' })) as Array<{ id: string; status: string }>;
    const ids = before.slice(0, 2).map((m) => m.id);
    await wrap('/api/admin/models/batch-status', { method: 'POST', body: { ids, status: 'retired' } });
    const after = (await wrap('/api/admin/models', { method: 'GET' })) as Array<{ id: string; status: string }>;
    ids.forEach((id) => {
      const m = after.find((x) => x.id === id);
      expect(m?.status).toBe('retired');
    });

    const deleteId = after[after.length - 1].id;
    await wrap(`/api/admin/models/${deleteId}`, { method: 'DELETE' });
    const final = (await wrap('/api/admin/models', { method: 'GET' })) as Array<{ id: string }>;
    expect(final.find((m) => m.id === deleteId)).toBeUndefined();
  });
});
