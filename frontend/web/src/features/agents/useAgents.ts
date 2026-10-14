/**
 * 管理侧「智能体工作台」hooks — 列表 / CRUD / 评测 / 版本对比 / 导入导出。
 */
import { useApiQuery, useApiMutation } from '@/services/query';
import { qk } from '@/api/shared/query-keys';
import type {
  AgentEntry, AgentFilters, EvalCase, EvalResult, DiffRequest, DiffResult, PromptDocs,
  CreateAgentVars, UpdateAgentVars, BatchStatusVars, DeleteAgentsVars,
  ToggleStarVars, RunEvalVars, ExportRequestVars, ImportConfirmVars,
} from './schema';

const ROOT = qk.admin.agents.root;

export function useAgentsList(filters: AgentFilters = {}) {
  return useApiQuery<AgentEntry[]>(
    [...qk.admin.agents.list],
    '/api/admin/agents',
    { query: filters as Record<string, unknown> },
    { staleTime: 30_000, placeholderData: (prev) => prev },
  );
}

export function useAgentDetail(id: string) {
  return useApiQuery<AgentEntry>(
    [...qk.admin.agents.detail(id)],
    `/api/admin/agents/${id}`,
    {},
    { enabled: id.length > 0 },
  );
}

export function useAgentVersions(id: string) {
  return useApiQuery<{ agentId: string; versions: AgentEntry['versions'] }>(
    [...qk.admin.agents.versions(id)],
    `/api/admin/agents/${id}/versions`,
    {},
    { enabled: id.length > 0 },
  );
}

export function useAgentEvalHistory(id: string) {
  return useApiQuery<{ agentId: string; runs: Array<{ runId: string; passRate: number; failedCases: number; at: string }> }>(
    [...qk.admin.agents.evaluations(id)],
    `/api/admin/agents/${id}/evaluations`,
    {},
    { enabled: id.length > 0 },
  );
}

export function useCreateAgent() {
  return useApiMutation<AgentEntry, CreateAgentVars>(
    '/api/admin/agents',
    { invalidateKeys: [ROOT] },
  );
}

export function useUpdateAgent() {
  return useApiMutation<AgentEntry, UpdateAgentVars>(
    (v) => `/api/admin/agents/${v.id}`,
    { invalidateKeys: [ROOT] },
    'PATCH',
  );
}

export function useDeleteAgents() {
  return useApiMutation<{ ids: string[] }, DeleteAgentsVars>(
    '/api/admin/agents/bulk-delete',
    { invalidateKeys: [ROOT] },
    'DELETE',
  );
}

export function useBatchSetStatus() {
  return useApiMutation<{ ids: string[] }, BatchStatusVars>(
    '/api/admin/agents/batch-status',
    { invalidateKeys: [ROOT] },
  );
}

export function useToggleStar() {
  return useApiMutation<AgentEntry, ToggleStarVars>(
    (v) => `/api/admin/agents/${v.id}/star`,
    { invalidateKeys: [ROOT] },
  );
}

export function useRunEval() {
  return useApiMutation<EvalResult, RunEvalVars>(
    (v) => `/api/admin/agents/${v.id}/eval`,
    { invalidateKeys: [ROOT] },
  );
}

export function useDiffVersions() {
  return useApiMutation<DiffResult, DiffRequest>(
    '/api/admin/agents/diff',
    {},
  );
}

export function useImportAgents() {
  return useApiMutation<{ created: number }, ImportConfirmVars>(
    '/api/admin/agents/import',
    { invalidateKeys: [ROOT] },
  );
}

export function useExportAgents() {
  // The backend returns the exported agent rows as a JSON response with an
  // attachment disposition; it does not return a client-side URL envelope.
  return useApiMutation<AgentEntry[], ExportRequestVars>(
    '/api/admin/agents/export',
    {},
  );
}

export type { AgentEntry, PromptDocs, EvalCase };
