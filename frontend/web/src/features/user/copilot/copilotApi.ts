import { getApiClient } from '@qzdap/web-api';
import type { CopilotSession } from './schema';
import type { SessionDetail } from './useCopilot';

export type ChatMessage = {
  role: 'user' | 'assistant';
  content: string;
  tools?: string[];
  compacted?: boolean;
};

export async function listCopilotSessions(): Promise<CopilotSession[]> {
  const rows = await getApiClient().get<CopilotSession[] | null>('/api/sessions');
  if (rows == null) return [];
  if (!Array.isArray(rows)) throw new Error('后端会话列表格式错误');
  return rows;
}

export async function createCopilotSession(agentId: string, title?: string): Promise<SessionDetail | null> {
  return getApiClient().post<SessionDetail>('/api/sessions', { agentId, title });
}

export async function loadCopilotSession(id: string): Promise<SessionDetail | null> {
  return getApiClient().get<SessionDetail>(`/api/sessions/${id}`);
}

export async function deleteCopilotSession(id: string): Promise<void> {
  await getApiClient().delete<void>(`/api/sessions/${id}`);
}

export async function streamCopilotTurn(
  sessionId: string,
  content: string,
  onEvent: (event: string, data: Record<string, unknown>) => void,
): Promise<void> {
  const client = getApiClient();
  for await (const item of client.streamEvents(`/api/sessions/${sessionId}/turns/stream`, { content })) {
    const data = (item.data && typeof item.data === 'object' ? item.data : {}) as Record<string, unknown>;
    if (item.event === 'error') throw new Error(String(data.message || data.error || '后端执行失败'));
    onEvent(item.event, data);
  }
}

export async function decideCopilotApproval(
  sessionId: string,
  approvalId: string,
  approved: boolean,
  onEvent: (event: string, data: Record<string, unknown>) => void,
): Promise<void> {
  const client = getApiClient();
  const verb = approved ? 'approve' : 'deny';
  for await (const item of client.streamEvents(`/api/sessions/${sessionId}/approvals/${approvalId}/${verb}`, {})) {
    const data = (item.data && typeof item.data === 'object' ? item.data : {}) as Record<string, unknown>;
    if (item.event === 'error') throw new Error(String(data.message || data.error || '后端执行失败'));
    onEvent(item.event, data);
  }
}
