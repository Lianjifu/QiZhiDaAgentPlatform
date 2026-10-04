/**
 * MetricsPage — 对齐技能/模型管理：无子模块 Tab，Hero 轻量，工具栏承载视图与时间范围。
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Download, Plus, Search } from 'lucide-react';
import { AdminListPagination, paginateItems } from '@/components/feedback/AdminListPagination';
import { AdminListHeader, AdminListHeaderMetrics } from '@/components/feedback/AdminListRow';
import { NoticeBanner } from '@/components/feedback/NoticeBanner';
import { TimeRangeDropdown } from '@/components/TimeRangeDropdown';
import {
  useModelMetrics, useLatencyPoints, useCostBreakdown, useMetricsDashboards, useThresholdRules,
} from './useMetrics';
import type {
  CostBreakdown, LatencyPoint, MetricsDashboard, ModelMetric, ThresholdRule,
} from './schema';
import { TIME_RANGES } from './components/constants';
import { ModelCard } from './components/ModelCard';
import { ExportMetricModal } from './components/ExportMetricModal';
import { BatchToolbar } from './components/BatchToolbar';
import { AvailabilityTab } from './components/tabs/AvailabilityTab';
import { LatencyTab } from './components/tabs/LatencyTab';
import { TokenTab } from './components/tabs/TokenTab';
import { DashboardTab } from './components/tabs/DashboardTab';

type ViewId = 'model' | 'availability' | 'latency' | 'token' | 'dashboard';

const VIEW_OPTIONS: Array<{ id: ViewId; label: string }> = [
  { id: 'model', label: '模型健康' },
  { id: 'availability', label: '可用率' },
  { id: 'latency', label: '延迟分析' },
  { id: 'token', label: 'Token 与成本' },
  { id: 'dashboard', label: '看板与告警' },
];

const EMPTY_MODELS: ModelMetric[] = [];
const EMPTY_DASHBOARDS: MetricsDashboard[] = [];
const EMPTY_RULES: ThresholdRule[] = [];
const EMPTY_LATENCY: LatencyPoint[] = [];
const EMPTY_BREAKDOWN: CostBreakdown[] = [];

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function MetricsPage() {
  const navigate = useNavigate();
  const [view, setView] = useState<ViewId>('model');
  const [search, setSearch] = useState('');
  const [range, setRange] = useState<typeof TIME_RANGES[number]['id']>('24h');
  const [exportOpen, setExportOpen] = useState(false);
  const [pickedDashboards, setPickedDashboards] = useState<Set<string>>(new Set());
  const [notice, setNotice] = useState('');
  const [page, setPage] = useState(1);

  const models = useModelMetrics();
  const latency = useLatencyPoints();
  const breakdown = useCostBreakdown();
  const dashboards = useMetricsDashboards();
  const rules = useThresholdRules();

  const remoteModels = models.data ?? EMPTY_MODELS;
  const remoteDashboards = useMemo(() => dashboards.data ?? EMPTY_DASHBOARDS, [dashboards.data]);
  const remoteRules = useMemo(() => rules.data ?? EMPTY_RULES, [rules.data]);
  const remoteLatency = latency.data ?? EMPTY_LATENCY;
  const remoteBreakdown = breakdown.data ?? EMPTY_BREAKDOWN;

  const [localDashboards, setLocalDashboards] = useState(remoteDashboards);
  const [localRules, setLocalRules] = useState(remoteRules);
  useEffect(() => { setLocalDashboards(remoteDashboards); }, [remoteDashboards]);
  useEffect(() => { setLocalRules(remoteRules); }, [remoteRules]);

  const enabledRules = useMemo(() => localRules.filter((r) => r.enabled).length, [localRules]);

  const visibleModels = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return remoteModels;
    return remoteModels.filter((m) =>
      `${m.model} ${m.provider}`.toLowerCase().includes(q),
    );
  }, [remoteModels, search]);

  useEffect(() => { setPage(1); }, [search, view, range]);
  const paged = useMemo(() => paginateItems(visibleModels, page), [visibleModels, page]);

  const toggleStar = (id: string) => {
    setLocalDashboards((prev) => prev.map((d) => (d.id === id ? { ...d, starred: !d.starred } : d)));
  };
  const toggleRule = (id: string) => {
    setLocalRules((prev) => prev.map((r) => (r.id === id ? { ...r, enabled: !r.enabled } : r)));
  };
  const togglePick = (id: string) => {
    setPickedDashboards((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const flash = (text: string) => {
    setNotice(text);
    window.setTimeout(() => setNotice(''), 2400);
  };

  const handleSelectModel = (m: ModelMetric) => navigate(`/admin/metrics/${m.id}`);
  const goMetricDetail = (id: string) => navigate(`/admin/metrics/${id}`);

  const handleExportOne = (m: ModelMetric) => {
    downloadBlob(new Blob([JSON.stringify(m, null, 2)], { type: 'application/json' }), `metric-${m.id}.json`);
    flash(`已导出「${m.model}」指标。`);
  };

  const viewSelect = (
    <select
      aria-label="视图"
      value={view}
      onChange={(e) => setView(e.target.value as ViewId)}
      className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-xs outline-none focus:border-[var(--brand)]"
    >
      {VIEW_OPTIONS.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
    </select>
  );

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-10">
      <section className="relative overflow-hidden rounded-[28px] border border-[var(--border)] bg-[var(--surface-1)] px-6 py-8 shadow-[var(--shadow-sm)] sm:px-8">
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden rounded-[28px]">
          <div className="absolute right-0 top-0 h-full w-1/2 bg-[radial-gradient(circle_at_top_right,rgba(99,102,241,0.10),transparent_68%)]" />
        </div>
        <div className="relative">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-indigo-700 dark:text-indigo-300">ADMIN / 运行指标</p>
          <h2 className="mt-3 text-2xl font-semibold tracking-tight sm:text-3xl xl:text-4xl">观测可用率、延迟和成本。</h2>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-[var(--text-muted)]">{remoteModels.length} 个模型 · {remoteDashboards.length} 个看板 · {enabledRules} 条激活阈值。</p>
        </div>
      </section>

      {notice && (
        <NoticeBanner tone="violet" onClose={() => setNotice('')}>
          {notice}
        </NoticeBanner>
      )}

      {view === 'dashboard' && pickedDashboards.size > 0 && (
        <BatchToolbar
          count={pickedDashboards.size}
          onEnable={() => { flash(`已启用 ${pickedDashboards.size} 个看板`); setPickedDashboards(new Set()); }}
          onDisable={() => { flash(`已停用 ${pickedDashboards.size} 个看板`); setPickedDashboards(new Set()); }}
          onDelete={() => { flash(`已删除 ${pickedDashboards.size} 个看板`); setPickedDashboards(new Set()); }}
        />
      )}

      {view === 'model' && (
        <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
          <div className="flex flex-col gap-2 border-b border-[var(--border)] px-4 py-3 sm:flex-row sm:items-center sm:px-5">
            <label className="relative min-w-0 flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-muted)]" />
              <input
                aria-label="搜索模型"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="搜索模型 / 提供商"
                className="h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] pl-8 pr-3 text-sm outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--brand)]"
              />
            </label>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              {viewSelect}
              <TimeRangeDropdown value={range} onChange={setRange} options={TIME_RANGES} />
              <button
                type="button"
                onClick={() => setExportOpen(true)}
                className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-3 text-xs font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]"
              >
                <Download className="h-3.5 w-3.5" />导出
              </button>
              <button
                type="button"
                onClick={() => navigate('/admin/metrics/new')}
                className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]"
              >
                <Plus className="h-3.5 w-3.5" />新建看板
              </button>
            </div>
          </div>
          <AdminListHeader hasCheckbox={false} hasStar={false} metrics={<AdminListHeaderMetrics labels={['可用率', 'P95', '错误率', '调用']} />} />
          <div className="divide-y divide-[var(--border)]">
            {paged.slice.map((m) => (
              <ModelCard
                key={m.id}
                model={m}
                onSelect={handleSelectModel}
                onExportOne={handleExportOne}
              />
            ))}
          </div>
          <AdminListPagination
            page={paged.safePage}
            totalPages={paged.totalPages}
            total={paged.total}
            pageStart={paged.pageStart}
            pageEnd={paged.pageEnd}
            onPageChange={setPage}
          />
          {visibleModels.length === 0 && (
            <div className="px-5 pb-8 text-center">
              <Search className="mx-auto h-6 w-6 text-[var(--text-muted)]" />
              <p className="mt-3 text-sm font-semibold">没有匹配的模型</p>
              <p className="mt-1 text-xs text-[var(--text-muted)]">尝试其他关键词或清除筛选。</p>
            </div>
          )}
        </div>
      )}

      {view !== 'model' && (
        <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
          <div className="flex flex-wrap items-center gap-2 border-b border-[var(--border)] px-4 py-3 sm:px-5">
            {viewSelect}
            {view !== 'dashboard' && (
              <TimeRangeDropdown value={range} onChange={setRange} options={TIME_RANGES} />
            )}
            {view === 'dashboard' && (
              <>
                <button
                  type="button"
                  onClick={() => setExportOpen(true)}
                  className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-3 text-xs font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]"
                >
                  <Download className="h-3.5 w-3.5" />导出
                </button>
                <button
                  type="button"
                  onClick={() => navigate('/admin/metrics/new')}
                  className="ml-auto inline-flex h-9 items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]"
                >
                  <Plus className="h-3.5 w-3.5" />新建看板
                </button>
              </>
            )}
          </div>
          <div className="p-5 sm:p-7">
            {view === 'availability' && (
              <AvailabilityTab models={remoteModels} onSelect={goMetricDetail} />
            )}
            {view === 'latency' && (
              <LatencyTab latency={remoteLatency} models={remoteModels} onSelect={goMetricDetail} />
            )}
            {view === 'token' && (
              <TokenTab models={remoteModels} breakdown={remoteBreakdown} />
            )}
            {view === 'dashboard' && (
              <DashboardTab
                dashboards={localDashboards}
                rules={localRules}
                pickedIds={pickedDashboards}
                onTogglePick={togglePick}
                onToggleStar={toggleStar}
                onCreate={() => navigate('/admin/metrics/new')}
                onToggleRule={toggleRule}
              />
            )}
          </div>
        </div>
      )}

      <ExportMetricModal
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        onExport={(sections) => { flash(`已导出 ${sections.length} 个区段`); setExportOpen(false); }}
      />

      <p className="text-center text-xs text-[var(--text-muted)]">本页为前端演示数据,生产环境将接入企智搭指标中台。</p>
    </div>
  );
}
