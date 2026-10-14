import { useServerAction } from '@/services/useServerAction';
/**
 * ModelsPage — 对齐技能管理：无子模块 Tab，Hero 轻量，列表工具栏承载导入/新建。
 * 视图筛选：模型 / 提供商 / 路由 / 健康。
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, CircleAlert, KeyRound, LineChart, Plus, RefreshCw, Search, ShieldCheck, Trash2, Upload } from 'lucide-react';
import { AdminListPagination, paginateItems } from '@/components/feedback/AdminListPagination';
import { AdminListHeader, AdminListHeaderMetrics } from '@/components/feedback/AdminListRow';
import { NoticeBanner } from '@/components/feedback/NoticeBanner';
import {
  useModelsList, useProviders, useRouteRules, useHealthEvents,
  useUpdateModel, useDeleteModel, useToggleStar,
  useToggleRoute, useDeleteRoute, useBatchSetStatus,
} from './useModels';
import type { Model, ModelFilters, ExchangeFormat } from './schema';
import { STATUS_FILTER, TIER_FILTER, PROVIDER_BADGE, STRATEGY_META, TASK_LABEL, downloadBlob } from './components/constants';
import { ModelCard } from './components/ModelCard';
import { ImportModelModal, ExportModelModal, DeleteModelModal } from './components/ImportExportModals';
import { BatchToolbar } from './components/BatchToolbar';

type ViewId = 'model' | 'provider' | 'route' | 'health';

export default function ModelsPage() {
  const navigate = useNavigate();
  const [filters, setFilters] = useState<ModelFilters>({ search: '', status: 'all', tier: 'all' });
  const [view, setView] = useState<ViewId>('model');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [deleteTarget, setDeleteTarget] = useState<Model | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [notice, setNotice] = useState('');
  const server = useServerAction(setNotice);
  const [page, setPage] = useState(1);

  const modelsQ = useModelsList(filters);
  const providersQ = useProviders();
  const routesQ = useRouteRules();
  const healthQ = useHealthEvents();

  const models = useMemo(() => modelsQ.data ?? [], [modelsQ.data]);
  const providers = useMemo(() => providersQ.data ?? [], [providersQ.data]);
  const routes = useMemo(() => routesQ.data ?? [], [routesQ.data]);
  const health = useMemo(() => healthQ.data ?? [], [healthQ.data]);

  const updateModel = useUpdateModel();
  const deleteModel = useDeleteModel();
  const toggleStar = useToggleStar();
  const toggleRoute = useToggleRoute();
  const deleteRoute = useDeleteRoute();
  const batchStatus = useBatchSetStatus();

  const counts = useMemo(() => {
    const total = models.length;
    const active = models.filter((m) => m.status === 'active').length;
    const calls = models.reduce((s, m) => s + m.calls, 0);
    return { total, active, calls };
  }, [models]);

  const visibleModels = useMemo(() => {
    const q = (filters.search ?? '').trim().toLowerCase();
    return models.filter((m) =>
      (filters.status === undefined || filters.status === 'all' || m.status === filters.status) &&
      (filters.tier === undefined || filters.tier === 'all' || m.tier === filters.tier) &&
      (q.length === 0 || `${m.name} ${m.providerName} ${m.description} ${m.tags.join(' ')}`.toLowerCase().includes(q)),
    );
  }, [models, filters]);

  useEffect(() => { setPage(1); }, [filters, view]);
  const paged = useMemo(() => paginateItems(visibleModels, page), [visibleModels, page]);

  const toggleSelect = (id: string) =>
    setSelectedIds((cur) => cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]);

  const openModel = (m: Model) => navigate(`/admin/models/${m.id}`);

  const handleDelete = (m: Model) => {
    deleteModel.mutate({ id: m.id }, { onSuccess: () => { setNotice(`已删除模型「${m.name}」。`); setDeleteTarget(null); } });
  };

  const handleToggleStar = (id: string) => {
    const m = models.find((x) => x.id === id);
    if (!m) return;
    toggleStar.mutate({ id, starred: !m.starred });
  };

  const handleEnable = (m: Model) => {
    if (m.status === 'active') return;
    updateModel.mutate({ id: m.id, patch: { status: 'active' } }, { onSuccess: () => setNotice(`已启用模型「${m.name}」。`) });
  };

  const handleExportOne = (m: Model) => {
    downloadBlob(new Blob([JSON.stringify(m, null, 2)], { type: 'application/json' }), `model-${m.id}.json`);
    setNotice(`已导出「${m.name}」。`);
  };

  const handleBatchEnable = () => {
    batchStatus.mutate({ ids: selectedIds, status: 'active' }, { onSuccess: () => { setNotice(`已批量启用 ${selectedIds.length} 个模型。`); setSelectedIds([]); } });
  };
  const handleBatchDisable = () => {
    batchStatus.mutate({ ids: selectedIds, status: 'retired' }, { onSuccess: () => { setNotice(`已批量下线 ${selectedIds.length} 个模型。`); setSelectedIds([]); } });
  };
  const handleBatchExport = () => setExportOpen(true);

  const handleImport = (_count: number, content: string, format: ExchangeFormat) => server.mutate({ path: '/api/admin/models/import', body: { content, format }, success: '已导入', onSuccess: () => setImportOpen(false) });

  const handleExport = (format: ExchangeFormat) => {
    const list = selectedIds.length > 0 ? models.filter((m) => selectedIds.includes(m.id)) : models;
    const payload = list.map((m) => ({ id: m.id, name: m.name, provider: m.providerName, status: m.status, priceIn: m.priceIn, priceOut: m.priceOut }));
    if (format === 'json') {
      downloadBlob(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }), 'models.json');
    } else {
      const yaml = payload.map((m) => `- id: "${m.id}"\n  name: "${m.name}"\n  status: "${m.status}"`).join('\n');
      downloadBlob(new Blob([`${yaml}\n`], { type: 'text/yaml' }), 'models.yaml');
    }
    setNotice(`已导出 ${list.length} 个模型为 ${format.toUpperCase()} 文件。`);
  };

  const handleRouteToggle = (id: string) => {
    toggleRoute.mutate({ id }, { onSuccess: () => setNotice('规则已更新。') });
  };

  const handleRouteDelete = (id: string) => {
    const r = routes.find((x) => x.id === id);
    deleteRoute.mutate({ id }, { onSuccess: () => setNotice('规则已删除。') });
  };

  const findModel = (id: string) => models.find((m) => m.id === id);

  const modelByProvider = useMemo(() => {
    const map = new Map<string, Model[]>();
    models.forEach((m) => {
      const arr = map.get(m.providerId) || [];
      arr.push(m);
      map.set(m.providerId, arr);
    });
    return map;
  }, [models]);

  return (
    <div className="models-page mx-auto w-full max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-10">
      <section className="relative overflow-hidden rounded-[28px] border border-[var(--border)] bg-[var(--surface-1)] px-6 py-8 shadow-[var(--shadow-sm)] sm:px-8">
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden rounded-[28px]">
          <div className="absolute right-0 top-0 h-full w-1/2 bg-[radial-gradient(circle_at_top_right,rgba(99,102,241,0.10),transparent_68%)]" />
        </div>
        <div className="relative">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-indigo-700 dark:text-indigo-300">ADMIN / 模型配置</p>
          <h2 className="mt-3 text-2xl font-semibold tracking-tight sm:text-3xl xl:text-4xl">接入模型并配置路由。</h2>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-[var(--text-muted)]">{counts.total} 个模型 · {counts.active} 启用 · 本月调用 {counts.calls.toLocaleString('zh-CN')}。</p>
        </div>
      </section>

      {notice && (
        <NoticeBanner tone="violet" onClose={() => setNotice('')}>
          {notice}
        </NoticeBanner>
      )}

      {selectedIds.length > 0 && view === 'model' && (
        <BatchToolbar
          count={selectedIds.length}
          onClear={() => setSelectedIds([])}
          onBatchEnable={handleBatchEnable}
          onBatchDisable={handleBatchDisable}
          onBatchExport={handleBatchExport}
        />
      )}

      {view === 'model' && (
        <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
          <div className="flex flex-col gap-2 border-b border-[var(--border)] px-4 py-3 sm:flex-row sm:items-center sm:px-5">
            <label className="relative min-w-0 flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-muted)]" />
              <input
                aria-label="搜索模型"
                value={filters.search ?? ''}
                onChange={(e) => setFilters((cur) => ({ ...cur, search: e.target.value }))}
                placeholder="搜索模型 / 提供商"
                className="h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] pl-8 pr-3 text-sm outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--brand)]"
              />
            </label>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              <select
                aria-label="视图"
                value={view}
                onChange={(e) => setView(e.target.value as ViewId)}
                className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-xs outline-none focus:border-[var(--brand)]"
              >
                <option value="model">模型列表</option>
                <option value="provider">提供商</option>
                <option value="route">路由策略</option>
                <option value="health">健康监控</option>
              </select>
              <select
                aria-label="状态"
                value={filters.status ?? 'all'}
                onChange={(e) => setFilters((cur) => ({ ...cur, status: e.target.value as ModelFilters['status'] }))}
                className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-xs outline-none focus:border-[var(--brand)]"
              >
                {STATUS_FILTER.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
              </select>
              <select
                aria-label="层级"
                value={filters.tier ?? 'all'}
                onChange={(e) => setFilters((cur) => ({ ...cur, tier: e.target.value as ModelFilters['tier'] }))}
                className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-xs outline-none focus:border-[var(--brand)]"
              >
                {TIER_FILTER.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
              </select>
              <button type="button" onClick={() => setImportOpen(true)} className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-3 text-xs font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]">
                <Upload className="h-3.5 w-3.5" />导入
              </button>
              <button type="button" onClick={() => navigate('/admin/models/new')} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]">
                <Plus className="h-3.5 w-3.5" />新建模型
              </button>
            </div>
          </div>
          <AdminListHeader metrics={<AdminListHeaderMetrics labels={['调用', '价格', '延迟', '任务']} />} />
          <div className="divide-y divide-[var(--border)]">
            {paged.slice.map((m) => (
              <ModelCard
                key={m.id}
                model={m}
                selected={selectedIds.includes(m.id)}
                onToggleSelect={toggleSelect}
                onSelect={openModel}
                onToggleStar={handleToggleStar}
                onEnable={handleEnable}
                onExportOne={handleExportOne}
                onRequestDelete={setDeleteTarget}
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
            <select
              aria-label="视图"
              value={view}
              onChange={(e) => setView(e.target.value as ViewId)}
              className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-xs outline-none focus:border-[var(--brand)]"
            >
              <option value="model">模型列表</option>
              <option value="provider">提供商</option>
              <option value="route">路由策略</option>
              <option value="health">健康监控</option>
            </select>
            {view === 'route' && (
              <button type="button" onClick={() => navigate('/admin/models/routes/new')} className="ml-auto inline-flex h-9 items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]">
                <Plus className="h-3.5 w-3.5" />新建路由
              </button>
            )}
          </div>

          {view === 'provider' && (
            <div className="space-y-3 p-5">
              {providers.map((p) => {
                const badge = PROVIDER_BADGE[p.status];
                const ms = modelByProvider.get(p.id) || [];
                return (
                  <article key={p.id} className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
                    <header className="flex flex-wrap items-center gap-2">
                      <h4 className="text-sm font-semibold">{p.name}</h4>
                      <span className="rounded-full bg-[var(--bg-elevated)] px-2 py-0.5 text-[10px] font-medium">{p.region}</span>
                      <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${badge.className}`}>
                        <span className={`h-1.5 w-1.5 rounded-full ${badge.dot}`} aria-hidden="true" />{badge.label}
                      </span>
                      <button type="button" onClick={() => server.mutate({ path: `/api/admin/models/providers/${p.id}/health-check`, success: '健康检查已完成' })} className="ml-auto inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] px-2.5 py-1 text-[10px] font-semibold hover:border-[var(--brand)]">
                        <RefreshCw className="h-3 w-3" />健康检查
                      </button>
                    </header>
                    <div className="mt-3 flex flex-wrap items-center gap-3 text-[11px]">
                      <span className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--bg-elevated)] px-2 py-1 font-mono">{p.baseUrl}</span>
                      <span className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--bg-elevated)] px-2 py-1 font-mono"><KeyRound className="h-3 w-3" />{p.apiKeyMasked}</span>
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-4">
                      <div><span className="text-[var(--text-muted)]">接入模型</span><br /><span className="font-semibold tabular-nums">{ms.length}</span></div>
                      <div><span className="text-[var(--text-muted)]">错误率</span><br /><span className={`font-semibold tabular-nums ${p.errorRate > 1 ? 'text-rose-600' : ''}`}>{p.errorRate}%</span></div>
                      <div><span className="text-[var(--text-muted)]">平均延迟</span><br /><span className="font-semibold tabular-nums">{p.avgLatencyMs || '—'}ms</span></div>
                      <div><span className="text-[var(--text-muted)]">当前 QPS</span><br /><span className="font-semibold tabular-nums">{p.qps}</span></div>
                    </div>
                  </article>
                );
              })}
            </div>
          )}

          {view === 'route' && (
            <div className="space-y-3 p-5">
              {routes.map((r) => {
                const sm = STRATEGY_META[r.strategy];
                const StrIcon = sm.icon;
                const primary = findModel(r.primaryModelId);
                return (
                  <article key={r.id} className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
                    <header className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={() => handleRouteToggle(r.id)}
                        aria-pressed={r.enabled}
                        className={`relative inline-flex h-5 w-9 items-center rounded-full transition ${r.enabled ? 'bg-[var(--brand)]' : 'bg-[var(--bg-elevated)]'}`}
                      >
                        <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition ${r.enabled ? 'translate-x-4' : 'translate-x-0.5'}`} />
                      </button>
                      <h4 className="text-sm font-semibold">{r.name}</h4>
                      <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${sm.tone}`}>
                        <StrIcon className="h-3 w-3" />{sm.label}
                      </span>
                      <span className="rounded-full bg-[var(--bg-elevated)] px-2 py-0.5 text-[10px] font-medium">{TASK_LABEL[r.task]}</span>
                      <span className="ml-auto inline-flex items-center gap-1.5 rounded-full bg-[var(--bg-elevated)] px-2 py-0.5 text-[10px] font-medium">优先级 {r.priority}</span>
                      <button type="button" onClick={() => handleRouteDelete(r.id)} aria-label="删除规则" className="grid h-7 w-7 place-items-center rounded-lg text-[var(--text-muted)] hover:bg-rose-50 hover:text-rose-600">
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </header>
                    <p className="mt-2 text-[11px] text-[var(--text-muted)]">{r.description}</p>
                    <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px]">
                      <span className="rounded-lg bg-[var(--bg-elevated)] px-2 py-1 font-semibold">主:{primary?.name ?? '未匹配'}</span>
                      {r.fallbackModelIds.map((id) => {
                        const m = findModel(id);
                        return <span key={id} className="rounded-lg bg-[var(--bg-elevated)] px-2 py-1 font-medium">降级:{m?.name || id}</span>;
                      })}
                    </div>
                  </article>
                );
              })}
            </div>
          )}

          {view === 'health' && (
            <ol className="relative space-y-4 border-l border-[var(--border)] p-5 pl-10">
              {health.map((e) => {
                const sevBadge = e.type === 'incident'
                  ? { label: '故障', className: 'bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300' }
                  : e.type === 'latency'
                    ? { label: '延迟', className: 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300' }
                    : e.type === 'quota'
                      ? { label: '配额', className: 'bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300' }
                      : { label: '恢复', className: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300' };
                const Icon = e.type === 'incident'
                  ? AlertTriangle
                  : e.type === 'latency'
                    ? LineChart
                    : e.type === 'quota'
                      ? CircleAlert
                      : ShieldCheck;
                return (
                  <li key={e.id} className="relative">
                    <span className="absolute -left-[26px] top-1 grid h-5 w-5 place-items-center rounded-full bg-[var(--surface-1)] ring-2 ring-[var(--brand)]">
                      <Icon className="h-3 w-3 text-[var(--brand)]" />
                    </span>
                    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-1)] p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${sevBadge.className}`}>{sevBadge.label}</span>
                        <span className="text-xs font-semibold">{e.providerName}</span>
                        <span className="ml-auto text-[11px] text-[var(--text-muted)]">{e.occurredAt}</span>
                      </div>
                      <p className="mt-2 text-[11px] leading-5 text-[var(--text-muted)]">{e.message}</p>
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      )}

      <DeleteModelModal
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget && handleDelete(deleteTarget)}
        model={deleteTarget}
      />
      <ImportModelModal open={importOpen} onClose={() => setImportOpen(false)} onImport={handleImport} />
      <ExportModelModal
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        onExport={handleExport}
        total={models.length}
        selectedCount={selectedIds.length}
      />
    </div>
  );
}
