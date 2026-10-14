import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiClient } from '@qzdap/web-api';

afterEach(() => vi.unstubAllGlobals());

describe('real API data boundary', () => {
  const client = () => new ApiClient('', () => null);

  it('preserves empty lists without filling demo rows', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true, data: [] })));
    vi.stubGlobal('fetch', fetch);
    expect(await client().get('/api/admin/skills')).toEqual([]);
    expect(fetch).toHaveBeenCalledOnce();
  });

  it('returns an empty result for a successful no-content response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    expect(await client().delete('/api/admin/skills/example')).toBeNull();
  });

  it('propagates network errors instead of returning local data', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')));
    await expect(client().get('/api/admin/skills')).rejects.toMatchObject({ code: 'E_NETWORK' });
  });

  it.each([200, 503])('rejects an error envelope with HTTP %s', async (status) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: false, error: { code: 'E_TEST', message: 'backend failed' } }), { status })));
    await expect(client().get('/api/admin/skills')).rejects.toMatchObject({ message: 'backend failed', status });
  });

  it('sends writes to the backend and rejects a failed write', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'not implemented' }), { status: 501 }));
    vi.stubGlobal('fetch', fetch);
    await expect(client().request('/api/admin/skills/example', { method: 'PATCH', body: { name: 'edited' } })).rejects.toMatchObject({ status: 501 });
    expect(fetch).toHaveBeenCalledWith('/api/admin/skills/example', expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ name: 'edited' }) }));
  });
});
