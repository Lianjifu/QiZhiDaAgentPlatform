import { getApiClient } from '@qzdap/web-api';
import type { CopilotSession } from './schema';
import type { SessionDetail } from './useCopilot';

export type ChatMessage = {
  role: 'user' | 'assistant';
  content: string;
  tools?: string[];
  compacted?: boolean;
};

export async function safeClient() {
  try {
    return getApiClient();
  } catch {
    return null;
  }
}

export async function listCopilotSessions(): Promise<CopilotSession[]> {
  const client = await safeClient();
  if (!client) return [];
  try {
    const rows = await client.request<CopilotSession[]>('/api/sessions');
    return Array.isArray(rows) ? rows : [];
  } catch {
    return [];
  }
}

export async function createCopilotSession(agentId: string, title?: string): Promise<SessionDetail | null> {
  const client = await safeClient();
  if (!client) return null;
  try {
    return await client.request<SessionDetail>('/api/sessions', {
      method: 'POST',
      body: { agentId, title },
    });
  } catch {
    return null;
  }
}

export async function loadCopilotSession(id: string): Promise<SessionDetail | null> {
  const client = await safeClient();
  if (!client) return null;
  try {
    return await client.request<SessionDetail>(`/api/sessions/${id}`);
  } catch {
    return null;
  }
}

export async function streamCopilotTurn(
  sessionId: string,
  content: string,
  onEvent: (event: string, data: Record<string, unknown>) => void,
): Promise<void> {
  const client = await safeClient();
  if (!client) throw new Error('no client');
  for await (const item of client.streamEvents(`/api/sessions/${sessionId}/turns/stream`, { content })) {
    const data = (item.data && typeof item.data === 'object' ? item.data : {}) as Record<string, unknown>;
    onEvent(item.event, data);
  }
}

export async function decideCopilotApproval(
  sessionId: string,
  approvalId: string,
  approved: boolean,
  onEvent: (event: string, data: Record<string, unknown>) => void,
): Promise<void> {
  const client = await safeClient();
  if (!client) throw new Error('no client');
  const verb = approved ? 'approve' : 'deny';
  for await (const item of client.streamEvents(`/api/sessions/${sessionId}/approvals/${approvalId}/${verb}`, {})) {
    const data = (item.data && typeof item.data === 'object' ? item.data : {}) as Record<string, unknown>;
    onEvent(item.event, data);
  }
}
