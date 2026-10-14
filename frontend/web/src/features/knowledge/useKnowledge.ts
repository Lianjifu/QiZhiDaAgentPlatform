/**
 * 管理侧「知识管理」hooks — 5 类实体的 list + 部分 mutation。
 * 端点 /api/admin/knowledge/* 始终通过真实 API 请求。
 */
import { useApiQuery, useApiMutation } from '@/services/query';
import { qk } from '@/api/shared/query-keys';
import type {
  Kb, Doc, Source, Task, EvalCase,
  CreateKbVars, CreateSourceVars, ToggleKbStatusVars, BatchKbVars,
} from './schema';

const PATH = '/api/admin/knowledge';

export function useKnowledgeBases() {
  return useApiQuery<Kb[]>(
    [...qk.admin.knowledge.root, 'kbs'],
    `${PATH}/kbs`,
    undefined,
    { staleTime: 30_000, placeholderData: (prev) => prev },
  );
}

export function useKnowledgeBase(id: string | null) {
  return useApiQuery<Kb | null>(
    [...qk.admin.knowledge.root, 'kb', id ?? 'none'],
    id ? `${PATH}/kbs/${id}` : `${PATH}/kbs/__noop__`,
    undefined,
    { enabled: Boolean(id), staleTime: 30_000 },
  );
}

export function useKnowledgeDocs() {
  return useApiQuery<Doc[]>(
    [...qk.admin.knowledge.root, 'docs'],
    `${PATH}/docs`,
    undefined,
    { staleTime: 30_000, placeholderData: (prev) => prev },
  );
}

export function useKnowledgeSources() {
  return useApiQuery<Source[]>(
    [...qk.admin.knowledge.root, 'sources'],
    `${PATH}/sources`,
    undefined,
    { staleTime: 30_000, placeholderData: (prev) => prev },
  );
}

export function useKnowledgeTasks() {
  return useApiQuery<Task[]>(
    [...qk.admin.knowledge.root, 'tasks'],
    `${PATH}/tasks`,
    undefined,
    { staleTime: 15_000, placeholderData: (prev) => prev },
  );
}

export function useKnowledgeEvalCases() {
  return useApiQuery<EvalCase[]>(
    [...qk.admin.knowledge.root, 'eval'],
    `${PATH}/eval`,
    undefined,
    { staleTime: 30_000 },
  );
}

export function useCreateKb() {
  return useApiMutation<Kb, CreateKbVars>(
    () => `${PATH}/kbs`,
    { invalidateKeys: [qk.admin.knowledge.root] },
    'POST',
  );
}

export function useCreateSource() {
  return useApiMutation<Source, CreateSourceVars>(
    () => `${PATH}/sources`,
    { invalidateKeys: [qk.admin.knowledge.root] },
    'POST',
  );
}

export function useToggleKbStatus() {
  return useApiMutation<Kb, ToggleKbStatusVars>(
    (vars) => `${PATH}/kbs/${vars.id}/toggle-status`,
    { invalidateKeys: [qk.admin.knowledge.root] },
    'POST',
  );
}

export function useBatchKb() {
  return useApiMutation<{ affected: number }, BatchKbVars>(
    () => `${PATH}/kbs/__batch__`,
    { invalidateKeys: [qk.admin.knowledge.root] },
    'POST',
  );
}
