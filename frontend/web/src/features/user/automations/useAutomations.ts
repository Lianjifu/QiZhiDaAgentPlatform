/**
 * 用户侧「我的工作流」hooks — 列表来自管理端已发布工作流的 catalog 投影。
 */
import { useApiQuery, useApiMutation } from '@/services/query';
import { qk } from '@/api/shared/query-keys';
import { withDefaults } from '@/api/shared/pagination';
import type { Flow, FlowRun, FlowListParams, ToggleFavoriteVars, RecordRunVars } from './schema';

const PATH = '/api/catalog/workflows';

export function useFlows(params: FlowListParams = {}) {
  const query = withDefaults(params);
  return useApiQuery<Flow[]>(
    [...qk.user.automations.list],
    PATH,
    { query },
    { staleTime: 15_000, placeholderData: (prev) => prev },
  );
}

export function useFlowRuns() {
  return useApiQuery<FlowRun[]>(
    [...qk.user.automations.runs],
    `${PATH}/__runs__`,
    undefined,
    { staleTime: 15_000 },
  );
}

export function useToggleFlowFavorite() {
  return useApiMutation<Flow, ToggleFavoriteVars>(
    (vars) => `${PATH}/${vars.id}/favorite`,
    { invalidateKeys: [qk.user.automations.root] },
    'POST',
  );
}

export function useRecordFlowRun() {
  return useApiMutation<FlowRun, RecordRunVars>(
    (vars) => `${PATH}/${vars.flowId}/run`,
    { invalidateKeys: [qk.user.automations.runs, qk.user.automations.root] },
    'POST',
  );
}
