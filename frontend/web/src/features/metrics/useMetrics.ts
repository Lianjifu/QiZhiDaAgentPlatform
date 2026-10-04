/**
 * AdminMetrics hooks — 5 个列表查询(models/latency/cost/dashboards/thresholds)+ stats helper。
 */
import { useApiQuery, useApiMutation } from '@/services/query';
import { qk } from '@/api/shared/query-keys';
import type {
  CostBreakdown, LatencyPoint, MetricsDashboard, MetricsStats, MetricsTimeRange, ModelMetric, ThresholdRule,
} from './schema';

export function useModelMetrics() {
  return useApiQuery<ModelMetric[]>([...qk.admin.metrics.models], '/api/admin/metrics/models', undefined, {
    staleTime: 30_000,
  });
}

export function useLatencyPoints() {
  return useApiQuery<LatencyPoint[]>([...qk.admin.metrics.latency], '/api/admin/metrics/latency', undefined, {
    staleTime: 60_000,
  });
}

export function useCostBreakdown() {
  return useApiQuery<CostBreakdown[]>([...qk.admin.metrics.costBreakdown], '/api/admin/metrics/cost-breakdown', undefined, {
    staleTime: 60_000,
  });
}

export function useMetricsDashboards() {
  return useApiQuery<MetricsDashboard[]>([...qk.admin.metrics.dashboards], '/api/admin/metrics/dashboards', undefined, {
    staleTime: 30_000,
  });
}

export function useThresholdRules() {
  return useApiQuery<ThresholdRule[]>([...qk.admin.metrics.thresholds], '/api/admin/metrics/thresholds', undefined, {
    staleTime: 30_000,
  });
}

export function useCreateDashboard() {
  return useApiMutation<MetricsDashboard, { name: string; range: MetricsTimeRange; description?: string }>(
    () => '/api/admin/metrics/dashboards',
    { invalidateKeys: [qk.admin.metrics.dashboards] },
    'POST',
  );
}

export function useMetricsStats(models: ModelMetric[]): MetricsStats {
  const total = models.length;
  const avgAvail = total > 0 ? models.reduce((s, m) => s + m.availability, 0) / total : 0;
  const avgP95 = Math.round(models.reduce((s, m) => s + m.p95, 0) / Math.max(total, 1));
  const totalInputTokens = models.reduce((s, m) => s + m.tokensIn, 0);
  const totalOutputTokens = models.reduce((s, m) => s + m.tokensOut, 0);
  const totalTokens = totalInputTokens + totalOutputTokens;
  const totalCost = models.reduce((s, m) => s + m.cost, 0);
  const errorRate = Math.round((models.reduce((s, m) => s + m.errorRate, 0) / Math.max(total, 1)) * 100) / 100;
  return { avgAvail, avgP95, totalTokens, totalCost, errorRate, totalInputTokens, totalOutputTokens };
}
