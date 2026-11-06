/**
 * Admin 额度详情 — 独立页面 /admin/quotas/:id
 */
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, CircleDollarSign, Save } from 'lucide-react';
import type { EnterpriseBudget } from './schema';
import { useQuotasBudgets, useQuotasDepartments, useUpdateBudget } from './useQuotas';
import {
  DrawerPanelAllocation,
  DrawerPanelDetail,
  DrawerPanelHistory,
  DrawerPanelTrend,
  DrawerSidebar,
} from './components/DrawerPanels';
import { BUDGET_BADGE, PERIOD_LABEL } from './components/constants';
import { AdminPage } from '@/components/feedback/AdminPage';

type DrawerPanel = 'detail' | 'trend' | 'allocation' | 'history';

function NotFound() {
  return (
    <AdminPage density="lg">
      <Link to="/admin/quotas" className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--brand)]">
        <ArrowLeft className="h-3.5 w-3.5" />返回额度管理
      </Link>
      <div className="rounded-2xl border border-dashed border-[var(--border)] bg-[var(--surface-1)] p-8 text-center">
        <p className="text-sm font-semibold">预算不存在或已被删除</p>
        <p className="mt-1 text-xs text-[var(--text-muted)]">请返回列表重新选择。</p>
      </div>
    </AdminPage>
  );
}

export default function QuotaDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: budgets = [] } = useQuotasBudgets();
  const { data: depts = [] } = useQuotasDepartments();
  const updateBudget = useUpdateBudget();

  const original = useMemo(() => budgets.find((b) => b.id === id), [budgets, id]);
  const [draft, setDraft] = useState<EnterpriseBudget | null>(null);
  const [panel, setPanel] = useState<DrawerPanel>('detail');

  useEffect(() => {
    setDraft(original ?? null);
    setPanel('detail');
  }, [original?.id]);

  if (!original || !draft) return <NotFound />;

  const badge = BUDGET_BADGE[draft.status];
  const update = (patch: Partial<EnterpriseBudget>) => setDraft({ ...draft, ...patch });

  const handleSave = () => {
    updateBudget.mutate({ id: draft.id, patch: draft }, { onSuccess: () => navigate('/admin/quotas') });
  };

  return (
    <AdminPage density="lg">
      <Link to="/admin/quotas" className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--brand)]">
        <ArrowLeft className="h-3.5 w-3.5" />返回额度管理
      </Link>

      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--brand)]">额度 · {PERIOD_LABEL[draft.period]}</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">{draft.name}</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--text-muted)]">{draft.description}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-[11px] font-semibold ${badge.className}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${badge.dot}`} aria-hidden="true" />
              {badge.label}
            </span>
            <span className="inline-flex items-center gap-1 rounded-full bg-[var(--bg-elevated)] px-2 py-1 text-[11px] font-medium">由 {draft.owner}</span>
          </div>
        </div>
        <span className="grid h-12 w-12 place-items-center rounded-2xl bg-[var(--brand-light)] text-[var(--brand)]">
          <CircleDollarSign className="h-5 w-5" />
        </span>
      </header>

      <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6">
        <div className="flex flex-col gap-5 sm:flex-row">
          <DrawerSidebar panel={panel} setPanel={setPanel} />
          <div className="flex-1 space-y-5 sm:pl-0">
            {panel === 'detail' && <DrawerPanelDetail budget={draft} onChange={update} />}
            {panel === 'trend' && <DrawerPanelTrend budget={draft} />}
            {panel === 'allocation' && <DrawerPanelAllocation budget={draft} depts={depts} />}
            {panel === 'history' && <DrawerPanelHistory budget={draft} />}
          </div>
        </div>
        <div className="mt-6 flex flex-wrap items-center justify-end gap-3 border-t border-[var(--border)] pt-5">
          <Link to="/admin/quotas" className="rounded-lg border border-[var(--border)] px-4 py-2 text-xs font-semibold">关闭</Link>
          <button type="button" onClick={handleSave} className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]">
            <Save className="h-3.5 w-3.5" />保存修改
          </button>
        </div>
      </section>
    </AdminPage>
  );
}
