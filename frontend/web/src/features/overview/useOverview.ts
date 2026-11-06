/**
 * 管理侧「运营总览」hooks — 一站式拉取 KPI / 趋势 / 告警 / 服务 / Top 智能体 + 单点趋势。
 */
import { useApiQuery } from '@/services/query';
import { qk } from '@/api/shared/query-keys';
import type { OverviewSummary, TrendSeries } from './schema';

export function useOverviewSummary() {
  return useApiQuery<OverviewSummary>(
    [...qk.admin.overview.summary],
    '/api/admin/overview/summary',
    {},
    { staleTime: 60_000, placeholderData: (prev) => prev },
  );
}

export function useOverviewTrend(range: string) {
  return useApiQuery<TrendSeries>(
    [...qk.admin.overview.trend(range)],
    `/api/admin/overview/trend/${range}`,
    {},
    { staleTime: 60_000, placeholderData: (prev) => prev },
  );
}
