/**
 * 用户侧「我的任务」hooks — 列表 + 单任务操作(完成/重试/归档)。
 */
import { useApiQuery, useApiMutation } from '@/services/query';
import { qk } from '@/api/shared/query-keys';
import { withDefaults } from '@/api/shared/pagination';
import type { Task, TaskListParams, UpdateTaskVars } from './schema';

const PATH = '/api/tasks';

export function useTasks(params: TaskListParams = {}) {
  const query = withDefaults(params);
  return useApiQuery<Task[]>(
    [...qk.user.tasks.list],
    PATH,
    { query },
    { staleTime: 30_000, placeholderData: (prev) => prev },
  );
}

export function useUpdateTask() {
  return useApiMutation<Task, UpdateTaskVars>(
    (vars) => `${PATH}/${vars.id}`,
    { invalidateKeys: [qk.user.tasks.root] },
    'POST',
  );
}