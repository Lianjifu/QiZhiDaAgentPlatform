import { useApiQuery } from '@/services/query';
import { CircleDollarSign, Save, ShieldCheck } from 'lucide-react';
import { useEffect, useState } from 'react';
import { SideDrawer } from '@/components/feedback/SideDrawer';
import type { DepartmentQuota, EnterpriseBudget, BudgetPeriod } from '../schema';
import { BUDGET_BADGE, DRAWER_NAV_ITEMS, PERIOD_LABEL } from './constants';
import { ProgressBar, Sparkline } from './Primitives';

type DrawerPanel = 'detail' | 'trend' | 'allocation' | 'history';

export function DrawerPanelDetail({ budget, onChange }: { budget: EnterpriseBudget; onChange: (patch: Partial<EnterpriseBudget>) => void }) {
  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">预算名称</label>
          <input type="text" value={budget.name} onChange={(e) => onChange({ name: e.target.value })} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
        </div>
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">周期</label>
          <select value={budget.period} onChange={(e) => onChange({ period: e.target.value as BudgetPeriod })} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]">
            {(Object.keys(PERIOD_LABEL) as BudgetPeriod[]).map((p) => <option key={p} value={p}>{PERIOD_LABEL[p]}</option>)}
          </select>
        </div>
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">总预算 (¥)</label>
          <input type="number" value={budget.totalCap} onChange={(e) => onChange({ totalCap: Number(e.target.value) })} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
        </div>
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">预警阈值 (%)</label>
          <input type="number" min={0} max={100} value={budget.alertThreshold} onChange={(e) => onChange({ alertThreshold: Number(e.target.value) })} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
        </div>
        <div className="sm:col-span-2">
          <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">说明</label>
          <textarea value={budget.description} onChange={(e) => onChange({ description: e.target.value })} rows={3} className="mt-1.5 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 py-2 text-sm outline-none focus:border-[var(--brand)]" />
        </div>
        <div className="sm:col-span-2 flex items-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] p-3">
          <button type="button" onClick={() => onChange({ rollover: !budget.rollover })} aria-pressed={budget.rollover} className={`relative inline-flex h-5 w-9 items-center rounded-full transition ${budget.rollover ? 'bg-[var(--brand)]' : 'bg-[var(--bg-elevated)]'}`}>
            <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition ${budget.rollover ? 'translate-x-4' : 'translate-x-0.5'}`} />
          </button>
          <div>
            <p className="text-xs font-semibold">余额结转</p>
            <p className="text-[11px] text-[var(--text-muted)]">开启后,本周期未使用的预算将结转到下周期。</p>
          </div>
        </div>
      </div>
    </div>
  );
}

export function DrawerPanelTrend({ budget }: { budget: EnterpriseBudget }) {
  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] p-5">
        <div className="flex items-center justify-between">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">累计消耗趋势</p>
          <p className="text-xs text-[var(--text-muted)]">12 个月</p>
        </div>
        <Sparkline data={[20, 32, 48, 60, 75, 92, 105, 120, 138, 158, 175, 192]} stroke="#6366f1" />
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] p-3"><p className="text-[10px] text-[var(--text-muted)]">日均</p><p className="mt-1 text-sm font-semibold tabular-nums">¥ {(budget.used / 100).toFixed(0)}</p></div>
        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] p-3"><p className="text-[10px] text-[var(--text-muted)]">峰值日</p><p className="mt-1 text-sm font-semibold tabular-nums">¥ {(budget.used / 30).toFixed(0)}</p></div>
        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] p-3"><p className="text-[10px] text-[var(--text-muted)]">预测结余</p><p className="mt-1 text-sm font-semibold tabular-nums">¥ {Math.max(0, budget.totalCap - budget.forecast).toLocaleString('zh-CN')}</p></div>
      </div>
    </div>
  );
}

export function DrawerPanelAllocation({ budget, depts }: { budget: EnterpriseBudget; depts: DepartmentQuota[] }) {
  const list = depts.filter((d) => d.enterpriseId === budget.id);
  const totalAllocated = list.reduce((s, d) => s + d.allocated, 0);
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-xs">
        <span className="font-semibold">已分配 ¥ {totalAllocated.toLocaleString('zh-CN')}</span>
        <span className="text-[var(--text-muted)]">总预算 ¥ {budget.totalCap.toLocaleString('zh-CN')}</span>
      </div>
      {list.map((d) => {
        const pct = Math.round((d.allocated / Math.max(budget.totalCap, 1)) * 100);
        return (
          <div key={d.id} className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] p-3 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-semibold">{d.name}</span>
              <span className="tabular-nums text-[var(--text-muted)]">¥ {d.allocated.toLocaleString('zh-CN')} · {pct}%</span>
            </div>
            <ProgressBar used={d.allocated} total={budget.totalCap} tone="violet" />
          </div>
        );
      })}
      {list.length === 0 && <p className="text-xs text-[var(--text-muted)]">此预算尚未分配给任何部门。</p>}
    </div>
  );
}

export function DrawerPanelHistory({ budget }: { budget: EnterpriseBudget }) {
  const { data: events = [] } = useApiQuery<{ time: string; actor: string; action: string }[]>(['detail', `/api/admin/quotas/budgets/${budget.id}/history`], `/api/admin/quotas/budgets/${budget.id}/history`);
  return (
    <ul className="space-y-2">
      {events.map((e, idx) => (
        <li key={idx} className="flex items-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface-1)] p-3">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-[var(--bg-elevated)] text-[var(--text-muted)]">
            <ShieldCheck className="h-4 w-4" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold">{e.action}</p>
            <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">{e.time} · 由 {e.actor}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function DrawerSidebar({ panel, setPanel }: { panel: DrawerPanel; setPanel: (p: DrawerPanel) => void }) {
  return (
    <nav aria-label="预算工作区" className="hidden w-[200px] shrink-0 flex-col gap-1 border-r border-[var(--border)] bg-[var(--bg-elevated)] p-4 sm:flex">
      <p className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">工作区</p>
      {DRAWER_NAV_ITEMS.map((item) => {
        const Icon = item.icon;
        const active = panel === item.id;
        return (
          <button key={item.id} type="button" onClick={() => setPanel(item.id)} aria-pressed={active} className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left text-xs font-semibold transition ${active ? 'bg-[var(--brand-light)] text-[var(--brand)]' : 'text-[var(--text-secondary)] hover:bg-[var(--surface-1)]'}`}>
            <Icon className="h-4 w-4" />
            {item.label}
          </button>
        );
      })}
    </nav>
  );
}

export function BudgetDetailDrawer({ budget, depts, onClose, onChange, onSave }: {
  budget: EnterpriseBudget | null;
  depts: DepartmentQuota[];
  onClose: () => void;
  onChange: (patch: Partial<EnterpriseBudget>) => void;
  onSave: () => void;
}) {
  const [panel, setPanel] = useState<DrawerPanel>('detail');
  useEffect(() => { setPanel('detail'); }, [budget?.id]);
  if (!budget) return null;
  const badge = BUDGET_BADGE[budget.status];
  return (
    <SideDrawer open={budget !== null} onClose={onClose} ariaLabel={`预算 ${budget.id}`} panelClassName="max-w-3xl" closeLabel="关闭预算详情" eyebrow={<div className="flex items-center gap-2"><span className="grid h-9 w-9 place-items-center rounded-lg bg-[var(--brand-light)] text-[var(--brand)]"><CircleDollarSign className="h-4 w-4" /></span><p className="text-[11px] font-semibold tracking-[0.2em] text-[var(--brand)]">额度管理</p></div>}>
      <div className="mt-8">
        <h3 className="text-2xl font-semibold">{budget.name}</h3>
        <p className="mt-2 text-sm leading-6 text-[var(--text-muted)]">{budget.description}</p>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-[11px] font-semibold ${badge.className}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${badge.dot}`} aria-hidden="true" />{badge.label}
          </span>
          <span className="rounded-full bg-[var(--bg-elevated)] px-2 py-1 text-[11px] font-medium">{PERIOD_LABEL[budget.period]}</span>
          <span className="rounded-full bg-[var(--bg-elevated)] px-2 py-1 text-[11px] font-medium">由 {budget.owner}</span>
        </div>
      </div>
      <div className="mt-8 flex flex-col sm:flex-row">
        <DrawerSidebar panel={panel} setPanel={setPanel} />
        <div className="flex-1 space-y-5 sm:pl-6">
          {panel === 'detail' && <DrawerPanelDetail budget={budget} onChange={onChange} />}
          {panel === 'trend' && <DrawerPanelTrend budget={budget} />}
          {panel === 'allocation' && <DrawerPanelAllocation budget={budget} depts={depts} />}
          {panel === 'history' && <DrawerPanelHistory budget={budget} />}
        </div>
      </div>
      <div className="mt-8 flex items-center justify-end gap-2 border-t border-[var(--border)] pt-5">
        <button type="button" onClick={onClose} className="rounded-lg border border-[var(--border)] px-4 py-2 text-xs font-semibold">关闭</button>
        <button type="button" onClick={onSave} className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]">
          <Save className="h-3.5 w-3.5" />保存修改
        </button>
      </div>
    </SideDrawer>
  );
}
