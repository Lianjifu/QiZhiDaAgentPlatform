import { getApiClient } from '@qzdap/web-api';
import type { CopilotSession } from './schema';
import type { SessionDetail } from './useCopilot';

export async function listCopilotSessions(params: { search?: string } = {}): Promise<CopilotSession[]> {
  const rows = await getApiClient().get<CopilotSession[] | null>('/api/sessions', {
    query: { search: params.search?.trim() || undefined },
  });
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
  signal?: AbortSignal,
  clientRequestId?: string,
): Promise<void> {
  const client = getApiClient();
  // 对话轮次可能跑很久 (多轮工具调用 + 沙箱执行), 默认 120s 会把流掐断.
  // 后端每 15s 发一次 keepalive 帧, 这里只需要比后端的静默窗口长.
  for await (const item of client.streamEvents(
    `/api/sessions/${sessionId}/turns/stream`,
    { content, ...(clientRequestId ? { clientRequestId } : {}) },
    { timeoutMs: 600_000, signal },
  )) {
    const data = (item.data && typeof item.data === 'object' ? item.data : {}) as Record<string, unknown>;
    if (item.event === 'error') throw new Error(String(data.message || data.error || '后端执行失败'));
    onEvent(item.event, data);
  }
}

export async function submitCopilotFeedback(
  sessionId: string,
  rating: 5 | 1,
  payload?: { turnId?: string; comment?: string; topic?: string },
): Promise<void> {
  await getApiClient().post(`/api/sessions/${sessionId}/feedback`, {
    rating,
    ...(payload ?? {}),
  });
}

export async function cancelCopilotTurn(sessionId: string): Promise<void> {
  await getApiClient().post<{ ok: boolean; cancelled: boolean }>(
    `/api/sessions/${sessionId}/cancel`,
    {},
  );
}

export async function decideCopilotApproval(
  sessionId: string,
  approvalId: string,
  approved: boolean,
  onEvent: (event: string, data: Record<string, unknown>) => void,
): Promise<void> {
  const client = getApiClient();
  const verb = approved ? 'approve' : 'deny';
  for await (const item of client.streamEvents(
    `/api/sessions/${sessionId}/approvals/${approvalId}/${verb}`,
    {},
    { timeoutMs: 600_000 },
  )) {
    const data = (item.data && typeof item.data === 'object' ? item.data : {}) as Record<string, unknown>;
    if (item.event === 'error') throw new Error(String(data.message || data.error || '后端执行失败'));
    onEvent(item.event, data);
  }
}
