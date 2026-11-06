/**
 * Copilot 会话 hooks。
 */
import { useApiQuery } from '@/services/query';
import { qk } from '@/api/shared/query-keys';
import { withDefaults } from '@/api/shared/pagination';
import type { ApiTurn, CopilotSession, SessionsListParams } from './schema';

const PATH = '/api/sessions';

export interface SessionDetail extends CopilotSession {
  messages?: Array<{ role: string; content: string; toolName?: string; turnId?: string }>;
  /** 每一轮的事实 ✓（耗时 / token / 成本 / 工具 / 知识命中 ✓）。 */
  turns?: ApiTurn[];
  /** 这个会话用的智能体 ✓（名字 / 模型 ✓）。 */
  agent?: { id?: string; name?: string; model?: string } | null;
  pendingApproval?: {
    approval_id?: string;
    approvalId?: string;
    tool_name?: string;
    toolName?: string;
    arguments?: Record<string, unknown>;
    reason?: string;
  } | null;
}

export function useSessions(params: SessionsListParams = {}) {
  const query = withDefaults(params);
  return useApiQuery<CopilotSession[]>(
    [...qk.user.copilot.sessions],
    PATH,
    { query },
    { staleTime: 15_000, placeholderData: (prev) => prev },
  );
}
