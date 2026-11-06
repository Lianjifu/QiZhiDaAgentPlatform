/**
 * 管理侧「运营总览」hooks — KPI / 趋势 / 告警（概览接口 ✓）+ 服务健康 / Top 智能体。
 *
 * ⚠️ **服务健康与 Top 智能体不走概览接口** ✓ ——
 * 概览接口只给 KPI 与告警 ✓；这两块是**真实数据** ✓：
 * 服务健康 ← 模型供应商健康（``/api/admin/models/providers`` ✓）
 * Top 智能体 ← 智能体调用量（``/api/admin/agents`` ✓）
 */
import { useApiMutation, useApiQuery } from '@/services/query';
import { qk } from '@/api/shared/query-keys';
import type { AgentEntry } from '@/features/agents/schema';
import type { Provider } from '@/features/models/schema';
import type { OverviewAlert, OverviewSummary, TrendSeries } from './schema';

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

/** 服务健康 —— 模型供应商的健康检查结果 ✓ */
export function useOverviewProviders() {
  return useApiQuery<Provider[]>(
    [...qk.admin.overview.root, 'providers'],
    '/api/admin/models/providers',
    {},
    { staleTime: 60_000, placeholderData: (prev) => prev },
  );
}

/** Top 智能体 —— 按调用量排序 ✓ */
export function useOverviewAgents() {
  return useApiQuery<AgentEntry[]>(
    [...qk.admin.overview.root, 'agents'],
    '/api/admin/agents',
    {},
    { staleTime: 60_000, placeholderData: (prev) => prev },
  );
}

export interface CreateOverviewAlertVars {
  severity: 'high' | 'medium' | 'low' | 'info';
  title: string;
  affected: string;
  suggestion: string;
}

/** 登记一条运维告警（写进概览的告警集合 ✓） */
export function useCreateOverviewAlert() {
  return useApiMutation<OverviewAlert, CreateOverviewAlertVars>(
    '/api/admin/overview/alerts',
    { invalidateKeys: [qk.admin.overview.summary] },
    'POST',
  );
}
