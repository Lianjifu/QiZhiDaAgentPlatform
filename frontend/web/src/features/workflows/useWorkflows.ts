/**
 * AdminWorkflows hooks — all reads and writes use the backend API.
 */
import {
  useApiMutation,
  useApiQuery,
} from '@/services/query';
import { qk } from '@/api/shared/query-keys';
import type { Flow } from './schema';

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
