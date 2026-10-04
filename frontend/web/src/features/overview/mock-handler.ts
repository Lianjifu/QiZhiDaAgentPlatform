/**
 * AdminOverview mock handler — 提供 /api/admin/overview/{summary,trend/:range,alerts} 端点。
 */
import type { OverviewSummary, Range, TrendSeries } from './schema';
import { mockAlerts, mockOverviewSummary, mockTrendByRange } from './fixtures';

function withDelay<T>(value: T, ms = 120) {
  return new Promise<T>((resolve) => setTimeout(() => resolve(value), ms));
}

export function wrapMockHandlerWithAdminOverview(
  fallback: (path: string, opts: any) => Promise<unknown> | unknown,
) {
  const alerts = [...mockAlerts];
  const services = [...mockOverviewSummary.services];
  const topAgents = [...mockOverviewSummary.topAgents];
  const trends = { ...mockTrendByRange };
  return async (path: string, opts: any = {}) => {
    const method = (opts?.method ?? 'GET').toUpperCase();
    if (method === 'POST' && path === '/api/admin/overview/alerts') {
      const body = (opts.body ?? {}) as Record<string, string>;
      const item = {
        id: `oa-${Date.now()}`,
        severity: (body.severity as OverviewSummary['alerts'][number]['severity']) || 'info',
        title: body.title || '未命名告警',
        time: body.time || '刚刚',
        affected: body.affected || '工作空间',
        suggestion: body.suggestion || '',
      };
      alerts.unshift(item);
      return withDelay(item);
    }
    if (method === 'POST' && path === '/api/admin/overview/services') {
      const body = (opts.body ?? {}) as Record<string, string>;
      const item = {
        name: body.name || '未命名服务',
        status: (body.status as 'ok' | 'degraded' | 'down') || 'ok',
        latency: body.latency || '—',
        detail: body.detail || '',
      };
      services.unshift(item);
      return withDelay(item);
    }
    if (method === 'POST' && path === '/api/admin/overview/top-agents') {
      const body = (opts.body ?? {}) as Record<string, unknown>;
      const item = {
        name: String(body.name || '未命名智能体'),
        calls: String(body.calls || '0'),
        share: Number(body.share || 0),
        tone: (body.tone as 'brand') || 'brand',
      };
      topAgents.unshift(item);
      return withDelay(item);
    }
    const putTrend = /^\/api\/admin\/overview\/trend\/([\w]+)$/.exec(path);
    if (method === 'PUT' && putTrend) {
      const range = putTrend[1] as Range;
      const body = (opts.body ?? {}) as { points?: TrendSeries['points'] };
      const series = { range, points: body.points ?? trends[range]?.points ?? [] };
      trends[range] = series;
      return withDelay(series);
    }
    if (method !== 'GET') return fallback(path, opts);
    if (path === '/api/admin/overview/summary') {
      return withDelay<OverviewSummary>({
        kpis: mockOverviewSummary.kpis,
        alerts,
        services,
        topAgents,
      });
    }
    if (path === '/api/admin/overview/alerts') return withDelay(alerts);
    const trendMatch = /^\/api\/admin\/overview\/trend\/([\w]+)$/.exec(path);
    if (trendMatch) {
      const range = trendMatch[1] as Range;
      return withDelay(trends[range] ?? trends['24h']);
    }
    return fallback(path, opts);
  };
}