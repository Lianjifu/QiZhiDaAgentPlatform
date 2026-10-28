/**
 * 用户侧「智能体库」hooks — 列表来自管理端已开放智能体的 catalog 投影。
 */
import { useApiQuery, useApiMutation } from '@/services/query';
import { qk } from '@/api/shared/query-keys';
import { withDefaults } from '@/api/shared/pagination';
import type { Agent, AgentListParams, ToggleFavoriteVars } from './schema';

const PATH = '/api/catalog/agents';

export function useAgents(params: AgentListParams = {}) {
  const query = withDefaults(params);
  return useApiQuery<Agent[]>(
    [...qk.user.agents.list],
    PATH,
    { query },
    { staleTime: 15_000, placeholderData: (prev) => prev },
  );
}

export function useToggleAgentFavorite() {
  return useApiMutation<Agent, ToggleFavoriteVars>(
    (vars) => `${PATH}/${vars.id}/favorite`,
    { invalidateKeys: [qk.user.agents.root] },
    'POST',
  );
}
