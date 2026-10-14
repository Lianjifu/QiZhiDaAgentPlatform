import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiClient } from './index';

afterEach(() => vi.unstubAllGlobals());

function uploadForm() {
  const form = new FormData();
  form.append('file', new Blob(['evidence'], { type: 'text/plain' }), 'evidence.txt');
  return form;
}

describe('development backend contracts', () => {
  it('accepts the raw Copilot attachment response and sends multipart with scope headers', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 'attachment-1' }), {
      status: 201,
      headers: { 'Content-Type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetch);
    const client = new ApiClient('', () => 'token', undefined, () => ({ 'X-Workspace-Id': 'workspace-1' }));
    const form = uploadForm();
    await expect(client.upload('/api/sessions/session-1/attachments', form)).resolves.toEqual({ id: 'attachment-1' });
    expect(fetch).toHaveBeenCalledWith('/api/sessions/session-1/attachments', expect.objectContaining({
      method: 'POST', body: form,
      headers: { Authorization: 'Bearer token', 'X-Workspace-Id': 'workspace-1' },
    }));
  });

  it('also accepts a successful gateway upload envelope', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true, data: { id: 'attachment-2' } }))));
    await expect(new ApiClient('').upload('/api/sessions/s1/attachments', uploadForm())).resolves.toEqual({ id: 'attachment-2' });
  });

  it.each([200, 422])('rejects an upload failure with HTTP %i instead of completing the attachment', async (status) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: false, error: { code: 'VALIDATION_ERROR', message: 'attachment rejected' } }), { status })));
    await expect(new ApiClient('').upload('/api/sessions/s1/attachments', uploadForm())).rejects.toMatchObject({
      code: 'E_BAD_REQUEST', message: 'attachment rejected', status,
    });
  });

  it('passes through raw admin mutation responses and preserves deletion bodies', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ id: 'suite-1', starred: true })))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetch);
    const client = new ApiClient('');
    await expect(client.request('/api/admin/evaluations/suites/suite-1', { method: 'PATCH', body: { starred: true } })).resolves.toEqual({ id: 'suite-1', starred: true });
    await expect(client.request('/api/admin/evaluations/suites/bulk-delete', { method: 'DELETE', body: { ids: ['suite-1'] } })).resolves.toBeNull();
    expect(fetch.mock.calls[1]).toEqual(['/api/admin/evaluations/suites/bulk-delete', expect.objectContaining({
      method: 'DELETE', body: JSON.stringify({ ids: ['suite-1'] }),
    })]);
  });
});
