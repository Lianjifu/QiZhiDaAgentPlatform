/**
 * Admin 运行指标详情 — 独立页面 /admin/metrics/:id
 */
import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import type { MetricsDrawerPanel } from './schema';
import {
  useCostBreakdown, useLatencyPoints, useModelMetrics, useThresholdRules,
} from './useMetrics';
import { DRAWER_NAV } from './components/constants';
import { AlertPanel, BreakdownPanel, OverviewPanel, TrendPanel } from './components/DrawerPanels';

function NotFound() {
  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-10">
      <Link to="/admin/metrics" className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--brand)]">
        <ArrowLeft className="h-3.5 w-3.5" />返回运行指标
      </Link>
      <div className="rounded-2xl border border-dashed border-[var(--border)] bg-[var(--surface-1)] p-8 text-center">
        <p className="text-sm font-semibold">模型指标不存在或已被删除</p>
        <p className="mt-1 text-xs text-[var(--text-muted)]">请返回列表重新选择。</p>
      </div>
    </div>
  );
}

function DrawerSidebar({ panel, setPanel }: { panel: MetricsDrawerPanel; setPanel: (p: MetricsDrawerPanel) => void }) {
  return (
    <nav aria-label="指标工作区" className="hidden w-[200px] shrink-0 flex-col gap-1 rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] p-4 sm:flex">
      <p className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">工作区</p>
      {DRAWER_NAV.map((item) => {
        const Icon = item.icon;
        const active = panel === item.id;
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => setPanel(item.id)}
            aria-pressed={active}
            className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left text-xs font-semibold transition ${active ? 'bg-[var(--brand-light)] text-[var(--brand)]' : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]'}`}
          >
            <Icon className="h-4 w-4" />
            {item.label}
          </button>
        );
      })}
    </nav>
  );
}

export default function MetricDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const modelsQuery = useModelMetrics();
  const latencyQuery = useLatencyPoints();
  const breakdownQuery = useCostBreakdown();
  const rulesQuery = useThresholdRules();

  const models = modelsQuery.data ?? [];
  const latency = latencyQuery.data ?? [];
  const breakdown = breakdownQuery.data ?? [];
  const rules = rulesQuery.data ?? [];

  const model = useMemo(() => models.find((m) => m.id === id), [models, id]);
  const [panel, setPanel] = useState<MetricsDrawerPanel>('overview');

  useEffect(() => {
    setPanel('overview');
  }, [id]);

  if (!model) return <NotFound />;

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-10">
      <Link to="/admin/metrics" className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--brand)]">
        <ArrowLeft className="h-3.5 w-3.5" />返回运行指标
      </Link>

      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">{model.provider}</p>
          <h1 className="mt-1 font-mono text-3xl font-semibold tracking-tight">{model.model}</h1>
        </div>
      </header>

      <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6">
        <div className="flex flex-col gap-5 sm:flex-row">
          <DrawerSidebar panel={panel} setPanel={setPanel} />
          <div className="flex-1 space-y-5">
            {panel === 'overview' && <OverviewPanel model={model} />}
            {panel === 'breakdown' && <BreakdownPanel model={model} breakdown={breakdown} />}
            {panel === 'trend' && <TrendPanel points={latency} />}
            {panel === 'alert' && <AlertPanel model={model} rules={rules} />}
          </div>
        </div>
        <div className="mt-6 flex justify-end border-t border-[var(--border)] pt-5">
          <Link to="/admin/metrics" className="rounded-lg border border-[var(--border)] px-4 py-2 text-xs font-semibold">
            关闭
          </Link>
        </div>
      </section>

      <p className="text-center text-xs text-[var(--text-muted)]">本页为前端演示数据,生产环境将接入企智搭指标中台。</p>
    </div>
  );
}
