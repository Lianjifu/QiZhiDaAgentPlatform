/**
 * AdminOperations hooks — 会话 / span / 异常 / 类型统计 + 标记 / 批量 / 导出。
 */
import {
  useApiQuery,
} from '@/services/query';
import { qk } from '@/api/shared/query-keys';
import type {
  Incident, KindStat, Session, Span,
} from './schema';
export function useSessions() {
  return useApiQuery<Session[]>(
    [...qk.admin.operations.sessions],
    '/api/admin/operations/sessions',
    {},
    { staleTime: 30_000, placeholderData: (prev) => prev },
  );
}

export function useSpans() {
  return useApiQuery<Span[]>(
    [...qk.admin.operations.spans],
    '/api/admin/operations/spans',
    {},
    { staleTime: 60_000, placeholderData: (prev) => prev },
  );
}

export function useIncidents() {
  return useApiQuery<Incident[]>(
    [...qk.admin.operations.incidents],
    '/api/admin/operations/incidents',
    {},
    { staleTime: 30_000, placeholderData: (prev) => prev },
  );
}

export function useKindStats() {
  return useApiQuery<KindStat[]>(
    [...qk.admin.operations.kindStats],
    '/api/admin/operations/kind-stats',
    {},
    { staleTime: 60_000, placeholderData: (prev) => prev },
  );
}