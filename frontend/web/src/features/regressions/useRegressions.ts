/**
 * AdminRegressions — 回归追踪数据 hooks。
 * 列表 / 告警 / 时间线 走 useApiQuery;CRUD 走本地乐观更新。
 */
import { useApiQuery, useApiMutation } from '@/services/query';
import { qk } from '@/api/shared/query-keys';
import type { AlertRule, RegressionTrack, TimelineEvent } from './schema';

export function useRegressionTracks() {
  return useApiQuery<RegressionTrack[]>(
    [...qk.admin.regressions.list],
    '/api/admin/regressions/tracks',
    undefined,
    { staleTime: 60_000 },
  );
}

export function useRegressionAlerts() {
  return useApiQuery<AlertRule[]>(
    [...qk.admin.regressions.alerts],
    '/api/admin/regressions/alerts',
    undefined,
    { staleTime: 60_000 },
  );
}

export function useRegressionTimeline() {
  return useApiQuery<TimelineEvent[]>(
    [...qk.admin.regressions.timeline],
    '/api/admin/regressions/timeline',
    undefined,
    { staleTime: 60_000 },
  );
}

export function useCreateRegressionTrack() {
  return useApiMutation<RegressionTrack, Partial<RegressionTrack>>(
    () => '/api/admin/regressions/tracks',
    { invalidateKeys: [qk.admin.regressions.list] },
    'POST',
  );
}