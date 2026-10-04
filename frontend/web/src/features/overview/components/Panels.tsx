/**
 * 告警列表 + 服务健康 + Top 智能体 — 3 个 panel 共享相同的卡片外壳。
 */
import { useNavigate } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import type { OverviewAlert, OverviewService, TopAgent } from '../schema';
import { SEVERITY_BADGE, StatusDot } from './Primitives';

const BAR_CLASS: Record<TopAgent['tone'], string> = {
  brand: 'bg-[var(--brand)]',
  success: 'bg-[var(--chart-success)]',
  info: 'bg-[var(--chart-info)]',
  purple: 'bg-[var(--chart-purple)]',
  warn: 'bg-[var(--chart-warning)]',
};

export function AlertsPanel({ alerts, onSelect }: { alerts: OverviewAlert[]; onSelect: (alert: OverviewAlert) => void }) {
  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-7">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold">实时告警与待处理事件</h3>
          <p className="mt-1 text-xs text-[var(--text-muted)]">按严重度排序 · 点击查看详情</p>
        </div>
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-[var(--danger-bg)] text-[var(--danger)]">
          <span className="text-xs font-semibold">{alerts.filter((a) => a.severity === 'high').length}</span>
        </span>
      </div>
      <div className="mt-5 divide-y divide-[var(--border)]">
        {alerts.length === 0
          ? <p className="py-8 text-center text-sm text-[var(--text-muted)]">暂无告警。</p>
          : alerts.map((alert) => {
          const badge = SEVERITY_BADGE[alert.severity];
          return (
            <button key={alert.id} type="button" onClick={() => onSelect(alert)} className="flex w-full items-start gap-3 py-3 text-left transition hover:bg-[var(--bg-hover)]">
              <span className={`mt-0.5 inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${badge.className}`}>{badge.label}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-semibold">{alert.title}</span>
                <span className="mt-1 block text-xs text-[var(--text-muted)]">{alert.affected} · {alert.time}</span>
              </span>
              <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-[var(--text-muted)]" />
            </button>
          );
        })}
      </div>
      <p className="mt-4 text-xs text-[var(--text-muted)]">{alerts.length} 条事件 · 来自运营概览接口</p>
    </section>
  );
}

export function ServicesPanel({ services, onViewAll }: { services: OverviewService[]; onViewAll: () => void }) {
  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-7">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold">系统状态</h3>
          <p className="mt-1 text-xs text-[var(--text-muted)]">核心服务的健康检查 · 平均 30s 刷新</p>
        </div>
        <button type="button" onClick={onViewAll} className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--brand)] hover:underline">
          详情 <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="mt-5 divide-y divide-[var(--border)]">
        {services.length === 0
          ? <p className="py-8 text-center text-sm text-[var(--text-muted)]">暂无服务健康数据。</p>
          : services.map((service) => (
          <div key={service.name} className="flex items-center gap-4 py-3 first:pt-0 last:pb-0">
            <StatusDot status={service.status} />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold">{service.name}</p>
              <p className="mt-0.5 text-xs text-[var(--text-muted)]">{service.detail}</p>
            </div>
            <span className="rounded-full bg-[var(--bg-elevated)] px-2 py-1 text-[10px] font-semibold text-[var(--text-secondary)]">{service.status === 'ok' ? '健康' : service.status === 'degraded' ? '降级' : '异常'}</span>
            <span className="shrink-0 text-xs tabular-nums text-[var(--text-muted)]">{service.latency}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

export function TopAgentsPanel({ topAgents }: { topAgents: TopAgent[] }) {
  const navigate = useNavigate();
  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-7">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold">Top 智能体</h3>
          <p className="mt-1 text-xs text-[var(--text-muted)]">按 24h 调用量排序</p>
        </div>
        <button type="button" onClick={() => navigate('/admin/agents')} className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--brand)] hover:underline">
          全部 <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="mt-5 space-y-4">
        {topAgents.length === 0
          ? <p className="py-8 text-center text-sm text-[var(--text-muted)]">暂无智能体调用排名。</p>
          : topAgents.map((agent, index) => (
          <button key={agent.name} type="button" onClick={() => navigate('/admin/agents')} className="block w-full text-left transition hover:opacity-90">
            <div className="flex items-center justify-between text-xs">
              <span className="inline-flex items-center gap-2 font-semibold">
                <span className="grid h-5 w-5 place-items-center rounded-md bg-[var(--bg-elevated)] text-[10px] font-semibold text-[var(--text-muted)]">{index + 1}</span>
                {agent.name}
              </span>
              <span className="tabular-nums text-[var(--text-muted)]">{agent.calls}</span>
            </div>
            <div className="mt-2 h-1.5 rounded-full bg-[var(--bg-hover)]">
              <div className={`h-1.5 rounded-full ${BAR_CLASS[agent.tone]}`} style={{ width: `${Math.max(agent.share * 100, 6)}%` }} />
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}