/**
 * AdminWorkflows hooks — all reads and writes use the backend API.
 */
import { useApiMutation, useApiQuery } from '@/services/query';
import { qk } from '@/api/shared/query-keys';
import type { Flow, WorkflowStats } from './schema';

export function useWorkflows() {
  return useApiQuery<Flow[]>(
    [...qk.admin.workflows.list],
    '/api/admin/workflows',
    undefined,
    { staleTime: 60_000 },
  );
}

export function useWorkflow(id: string | null) {
  return useApiQuery<Flow | null>(
    [...qk.admin.workflows.list, id ?? 'none'],
    id ? `/api/admin/workflows/${id}` : '/api/admin/workflows/__noop__',
    undefined,
    { enabled: Boolean(id), staleTime: 60_000 },
  );
}

export function useCreateWorkflow() {
  return useApiMutation<Flow, Flow>(
    '/api/admin/workflows',
    { invalidateKeys: [qk.admin.workflows.root] },
  );
}

export function useUpdateWorkflow() {
  return useApiMutation<Flow, { id: string; patch: Partial<Flow> }>(
    (vars) => `/api/admin/workflows/${vars.id}`,
    { invalidateKeys: [qk.admin.workflows.root] },
    'PATCH',
  );
}

export function useDeleteWorkflow() {
  return useApiMutation<{ ok: true; id: string }, { id: string }>(
    (vars) => `/api/admin/workflows/${vars.id}`,
    { invalidateKeys: [qk.admin.workflows.root] },
    'DELETE',
  );
}

export function useWorkflowStats(flows: Flow[]): WorkflowStats {
  const total = flows.length;
  const published = flows.filter((f) => f.status === 'published').length;
  const draft = flows.filter((f) => f.status === 'draft').length;
  const calls = flows.reduce((sum, f) => sum + f.callCount, 0);
  return { total, published, draft, calls };
}
