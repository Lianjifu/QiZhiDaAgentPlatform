import { useServerAction } from '@/services/useServerAction';
/**
 * QuotasPage — 对齐模型管理：无子模块 Tab，Hero 轻量，列表工具栏承载导入/新建。
 * 视图筛选：企业预算 / 部门额度 / 用量分析 / 告警规则。
 */
import {
  ArrowDown, ArrowUp, ClipboardList, Plus, Search, Upload, UsersRound,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AdminListPagination, paginateItems } from '@/components/feedback/AdminListPagination';
import { AdminListHeader, AdminListHeaderMetrics } from '@/components/feedback/AdminListRow';
import { NoticeBanner } from '@/components/feedback/NoticeBanner';
import {
  useQuotasAlerts, useQuotasBudgets, useQuotasDepartments, useQuotasUsage,
  useToggleAlert, useUpdateBudget,
} from './useQuotas';
import type { EnterpriseBudget, ExchangeFormat } from './schema';
import { BatchToolbar } from './components/BatchToolbar';
import { BudgetCard } from './components/BudgetCard';
import { ExportBudgetModal, ImportBudgetModal } from './components/ImportExportModals';
import { CATEGORY_META, PERIOD_LABEL, SCOPE_LABEL, SEVERITY_BADGE, downloadBlob } from './components/constants';
import { ProgressBar, Sparkline } from './components/Primitives';

type ViewId = 'budget' | 'department' | 'usage' | 'alert';

export default function QuotasPage() {
  const navigate = useNavigate();
  const { data: budgets = [] } = useQuotasBudgets();
  const { data: depts = [] } = useQuotasDepartments();
  const { data: usage = [] } = useQuotasUsage();
  const { data: alerts = [] } = useQuotasAlerts();

  const updateBudget = useUpdateBudget();
  const toggleAlert = useToggleAlert();

  const [view, setView] = useState<ViewId>('budget');
  const [search, setSearch] = useState('');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [importOpen, setImportOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [notice, setNotice] = useState('');
  const server = useServerAction(setNotice);
  const [page, setPage] = useState(1);

  const totals = useMemo(() => {
    const cap = budgets.reduce((s, b) => s + b.totalCap, 0);
    const used = budgets.reduce((s, b) => s + b.used, 0);
    return { cap, used };
  }, [budgets]);

  const visibleBudgets = useMemo(() => {
    const q = search.trim().toLowerCase();
    return budgets.filter((b) => q.length === 0 || `${b.name} ${b.owner} ${b.description}`.toLowerCase().includes(q));
  }, [budgets, search]);

  useEffect(() => { setPage(1); }, [search, view]);
  const paged = useMemo(() => paginateItems(visibleBudgets, page), [visibleBudgets, page]);

  const toggleSelect = (id: string) =>
    setSelectedIds((current) => current.includes(id) ? current.filter((x) => x !== id) : [...current, id]);

  const openBudget = (b: EnterpriseBudget) => navigate(`/admin/quotas/${b.id}`);

  const handleFreeze = (b: EnterpriseBudget) => {
    if (b.status === 'frozen') return;
    updateBudget.mutate({ id: b.id, patch: { status: 'frozen' } }, { onSuccess: () => setNotice(`已冻结预算「${b.name}」。`) });
  };

  const handleExportOne = (b: EnterpriseBudget) => {
    downloadBlob(new Blob([JSON.stringify(b, null, 2)], { type: 'application/json' }), `budget-${b.id}.json`);
    setNotice(`已导出「${b.name}」。`);
  };

  const handleBatchFreeze = () => {
    void Promise.all(selectedIds.map((id) => updateBudget.mutateAsync({ id, patch: { status: 'frozen' } }))).then(() => { setNotice(`已批量冻结 ${selectedIds.length} 个预算。`); setSelectedIds([]); }).catch((error) => setNotice(`冻结失败：${String(error)}`));
  };

  const handleBatchExport = () => setExportOpen(true);

  const handleImport = (_count: number, content: string, format: ExchangeFormat) => server.mutate({ path: '/api/admin/quotas/budgets/import', body: { content, format }, success: '已导入', onSuccess: () => setImportOpen(false) });

  const handleExport = (format: ExchangeFormat) => {
    const list = selectedIds.length > 0 ? budgets.filter((b) => selectedIds.includes(b.id)) : budgets;
    const data = list.map((b) => ({ id: b.id, name: b.name, period: PERIOD_LABEL[b.period], totalCap: b.totalCap, used: b.used, owner: b.owner }));
    if (format === 'json') {
      downloadBlob(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }), 'budgets.json');
    } else if (format === 'yaml') {
      const yaml = data.map((b) => `- id: "${b.id}"\n  name: "${b.name}"\n  period: "${b.period}"`).join('\n');
      downloadBlob(new Blob([`${yaml}\n`], { type: 'text/yaml' }), 'budgets.yaml');
    } else {
      const header = 'id,name,period,totalCap,used,owner';
      const lines = data.map((b) => [b.id, b.name, b.period, b.totalCap, b.used, b.owner].join(','));
      downloadBlob(new Blob([[header, ...lines].join('\n')], { type: 'text/csv' }), 'budgets.csv');
    }
    setNotice(`已导出 ${list.length} 个预算为 ${format.toUpperCase()} 文件。`);
  };

  const handleAlertToggle = (id: string) => {
    toggleAlert.mutate({ id }, { onSuccess: () => setNotice('规则已更新。') });
  };

  return (
    <div className="quotas-page mx-auto w-full max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-10">
      <section className="relative overflow-hidden rounded-[28px] border border-[var(--border)] bg-[var(--surface-1)] px-6 py-8 shadow-[var(--shadow-sm)] sm:px-8">
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden rounded-[28px]">
          <div className="absolute right-0 top-0 h-full w-1/2 bg-[radial-gradient(circle_at_top_right,rgba(34,197,94,0.10),transparent_68%)]" />
        </div>
        <div className="relative">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-emerald-700 dark:text-emerald-300">ADMIN / 额度管理</p>
          <h2 className="mt-3 text-2xl font-semibold tracking-tight sm:text-3xl xl:text-4xl">控制预算、用量和告警。</h2>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-[var(--text-muted)]">总预算 ¥ {totals.cap.toLocaleString('zh-CN')} · 已用 ¥ {totals.used.toLocaleString('zh-CN')}。</p>
        </div>
      </section>

      {notice && (
        <NoticeBanner tone="violet" onClose={() => setNotice('')}>
          {notice}
        </NoticeBanner>
      )}

      {selectedIds.length > 0 && view === 'budget' && (
        <BatchToolbar
          count={selectedIds.length}
          onClear={() => setSelectedIds([])}
          onBatchFreeze={handleBatchFreeze}
          onBatchExport={handleBatchExport}
        />
      )}

      {view === 'budget' && (
        <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
          <div className="flex flex-col gap-2 border-b border-[var(--border)] px-4 py-3 sm:flex-row sm:items-center sm:px-5">
            <label className="relative min-w-0 flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-muted)]" />
              <input
                aria-label="搜索预算"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="搜索预算 / 负责人"
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
                <option value="budget">企业预算</option>
                <option value="department">部门额度</option>
                <option value="usage">用量分析</option>
                <option value="alert">告警规则</option>
              </select>
              <button type="button" onClick={() => setImportOpen(true)} className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-3 text-xs font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]">
                <Upload className="h-3.5 w-3.5" />导入
              </button>
              <button type="button" onClick={() => navigate('/admin/quotas/new')} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]">
                <Plus className="h-3.5 w-3.5" />新建预算
              </button>
            </div>
          </div>
          <AdminListHeader hasStar={false} metrics={<AdminListHeaderMetrics labels={['用量']} />} />
          <div className="divide-y divide-[var(--border)]">
            {paged.slice.map((b) => (
              <BudgetCard
                key={b.id}
                budget={b}
                selected={selectedIds.includes(b.id)}
                onToggleSelect={toggleSelect}
                onSelect={openBudget}
                onFreeze={handleFreeze}
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
          {visibleBudgets.length === 0 && (
            <div className="px-5 pb-8 text-center">
              <Search className="mx-auto h-6 w-6 text-[var(--text-muted)]" />
              <p className="mt-3 text-sm font-semibold">没有匹配的预算</p>
              <p className="mt-1 text-xs text-[var(--text-muted)]">尝试其他关键词或清除筛选。</p>
            </div>
          )}
        </div>
      )}

      {view !== 'budget' && (
        <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
          <div className="flex flex-wrap items-center gap-2 border-b border-[var(--border)] px-4 py-3 sm:px-5">
            <select
              aria-label="视图"
              value={view}
              onChange={(e) => setView(e.target.value as ViewId)}
              className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-xs outline-none focus:border-[var(--brand)]"
            >
              <option value="budget">企业预算</option>
              <option value="department">部门额度</option>
              <option value="usage">用量分析</option>
              <option value="alert">告警规则</option>
            </select>
            {view === 'department' && (
              <button type="button" onClick={() => setNotice('部门额度报告导出接口暂未提供。')} className="ml-auto inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-3 text-xs font-semibold hover:border-[var(--brand)]">
                <ClipboardList className="h-3.5 w-3.5" />生成报告
              </button>
            )}
            {view === 'alert' && (
              <button type="button" onClick={() => navigate('/admin/quotas/alerts/new')} className="ml-auto inline-flex h-9 items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]">
                <Plus className="h-3.5 w-3.5" />新建规则
              </button>
            )}
          </div>

          {view === 'department' && (
            <div className="space-y-3 p-5">
              {depts.map((d) => {
                const tone = d.pct >= 80 ? 'rose' : d.pct >= 60 ? 'amber' : 'emerald';
                return (
                  <article key={d.id} className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
                    <header className="flex flex-wrap items-center gap-2">
                      <span className="grid h-9 w-9 place-items-center rounded-lg bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300"><UsersRound className="h-4 w-4" /></span>
                      <h4 className="text-sm font-semibold">{d.name}</h4>
                      <span className="rounded-full bg-[var(--bg-elevated)] px-2 py-0.5 text-[10px] font-medium">{d.members} 人</span>
                      <span className="rounded-full bg-[var(--bg-elevated)] px-2 py-0.5 text-[10px] font-medium">{d.manager}</span>
                      <span className="ml-auto rounded-full bg-violet-50 px-2 py-0.5 text-[10px] font-semibold text-violet-700 dark:bg-violet-500/15 dark:text-violet-300">排名 {d.rank}</span>
                    </header>
                    <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-4">
                      <div><span className="text-[var(--text-muted)]">分配</span><br /><span className="font-semibold tabular-nums">¥ {d.allocated.toLocaleString('zh-CN')}</span></div>
                      <div><span className="text-[var(--text-muted)]">已用</span><br /><span className="font-semibold tabular-nums">¥ {d.used.toLocaleString('zh-CN')}</span></div>
                      <div><span className="text-[var(--text-muted)]">使用率</span><br /><span className="font-semibold tabular-nums">{d.pct}%</span></div>
                      <div><span className="text-[var(--text-muted)]">最近高峰</span><br /><span className="font-semibold">{d.lastSpikeAt}</span></div>
                    </div>
                    <div className="mt-3 flex items-center gap-2">
                      <Sparkline data={d.trend} stroke="#22c55e" />
                      <span className="rounded-lg bg-[var(--bg-elevated)] px-2 py-1 text-[10px] font-medium">Top:{d.topChannel}</span>
                    </div>
                    <div className="mt-3">
                      <ProgressBar used={d.used} total={d.allocated} tone={tone} />
                    </div>
                  </article>
                );
              })}
            </div>
          )}

          {view === 'usage' && (
            <div className="space-y-3 p-5">
              {usage.map((u) => {
                const meta = CATEGORY_META[u.category];
                const Icon = meta.icon;
                const pct = Math.round((u.used / u.total) * 100);
                return (
                  <article key={u.id} className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
                    <header className="flex flex-wrap items-center gap-2">
                      <span className={`grid h-9 w-9 place-items-center rounded-lg ${meta.tone}`}><Icon className="h-4 w-4" /></span>
                      <h4 className="text-sm font-semibold">{u.label}</h4>
                      <span className="rounded-full bg-[var(--bg-elevated)] px-2 py-0.5 text-[10px] font-medium">{u.used} / {u.total} {u.unit}</span>
                      <span className={`ml-auto inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${u.delta >= 0 ? 'bg-amber-50 text-amber-700' : 'bg-emerald-50 text-emerald-700'}`}>
                        {u.delta >= 0 ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />}{Math.abs(u.delta)}%
                      </span>
                    </header>
                    <div className="mt-3">
                      <ProgressBar used={u.used} total={u.total} tone={pct >= 80 ? 'rose' : pct >= 60 ? 'amber' : 'emerald'} />
                    </div>
                    <div className="mt-3 flex items-center justify-between">
                      <Sparkline data={u.trend} stroke="#22c55e" />
                      <p className="text-[10px] text-[var(--text-muted)]">过去 12 个月</p>
                    </div>
                  </article>
                );
              })}
            </div>
          )}

          {view === 'alert' && (
            <div className="space-y-3 p-5">
              {alerts.map((a) => {
                const sev = SEVERITY_BADGE[a.severity];
                return (
                  <article key={a.id} className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
                    <header className="flex flex-wrap items-center gap-2">
                      <button type="button" onClick={() => handleAlertToggle(a.id)} aria-pressed={a.enabled} className={`relative inline-flex h-5 w-9 items-center rounded-full transition ${a.enabled ? 'bg-[var(--brand)]' : 'bg-[var(--bg-elevated)]'}`}>
                        <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition ${a.enabled ? 'translate-x-4' : 'translate-x-0.5'}`} />
                      </button>
                      <h4 className="text-sm font-semibold">{a.name}</h4>
                      <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${sev.className}`}>
                        <span className={`h-1.5 w-1.5 rounded-full ${sev.dot}`} aria-hidden="true" />{sev.label}
                      </span>
                      <span className="rounded-full bg-[var(--bg-elevated)] px-2 py-0.5 text-[10px] font-medium">{SCOPE_LABEL[a.scope]}</span>
                      <span className="ml-auto inline-flex items-center gap-1.5 rounded-full bg-[var(--bg-elevated)] px-2 py-0.5 text-[10px] font-medium">静默 {a.cooldown}</span>
                    </header>
                    <p className="mt-2 text-[11px] text-[var(--text-muted)]">{a.description}</p>
                    <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px]">
                      <span className="rounded-lg bg-[var(--bg-elevated)] px-2 py-1 font-semibold">指标:{a.metric}</span>
                      <span className="rounded-lg bg-[var(--bg-elevated)] px-2 py-1 font-medium">阈值 ≥ {a.threshold}</span>
                      <span className="rounded-lg bg-[var(--bg-elevated)] px-2 py-1 font-medium">通知:{a.notify.join(', ')}</span>
                      <span className="rounded-lg bg-[var(--bg-elevated)] px-2 py-1 font-medium">最近触发:{a.lastTriggered}</span>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </div>
      )}

      <ImportBudgetModal open={importOpen} onClose={() => setImportOpen(false)} onImport={handleImport} />
      <ExportBudgetModal open={exportOpen} onClose={() => setExportOpen(false)} onExport={handleExport} total={budgets.length} selectedCount={selectedIds.length} />
    </div>
  );
}
