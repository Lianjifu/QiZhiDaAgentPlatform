import { act, renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiClient, setApiClient } from '@qzdap/web-api';
import { useInviteMember } from './useTeam';
import type { ReactNode } from 'react';

afterEach(() => vi.unstubAllGlobals());

describe('workspace invitation request', () => {
  it('invites through the scoped current workspace instead of a display name URL', async () => {
    const invitation = { id: 'invite-1', email: 'new@example.com', role: '成员', status: 'pending', deliveryStatus: 'not_configured' };
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(invitation), { status: 201 }));
    vi.stubGlobal('fetch', fetch);
    setApiClient(new ApiClient('', () => null, undefined, () => ({ 'X-Workspace-Id': 'workspace-uuid' })));
    const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    const { result } = renderHook(() => useInviteMember(), { wrapper });
    await act(async () => {
      await expect(result.current.mutateAsync({ team: '运营协作空间', email: 'new@example.com' })).resolves.toEqual(invitation);
    });
    expect(fetch).toHaveBeenCalledWith('/api/workspaces/current/members/invite', expect.objectContaining({
      method: 'POST', body: JSON.stringify({ team: '运营协作空间', email: 'new@example.com' }),
      headers: expect.objectContaining({ 'X-Workspace-Id': 'workspace-uuid' }),
    }));
    client.clear();
  });
});
