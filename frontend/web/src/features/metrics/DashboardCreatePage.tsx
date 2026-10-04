/**
 * 新建看板 — 独立页面 /admin/metrics/new
 */
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, LayoutDashboard } from 'lucide-react';
import type { MetricsTimeRange } from './schema';
import { TIME_RANGES } from './components/constants';
import { useCreateDashboard } from './useMetrics';

export default function DashboardCreatePage() {
  const navigate = useNavigate();
  const createDashboard = useCreateDashboard();
  const [name, setName] = useState('');
  const [range, setRange] = useState<MetricsTimeRange>('24h');
  const [desc, setDesc] = useState('');
  const canSubmit = name.trim().length > 0;

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-10">
      <Link to="/admin/metrics" className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--brand)]">
        <ArrowLeft className="h-3.5 w-3.5" />返回运行指标
      </Link>
      <header>
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--brand)]">运行指标</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">新建看板</h1>
        <p className="mt-2 max-w-2xl text-sm text-[var(--text-muted)]">配置看板名称与默认时间范围。</p>
      </header>
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6">
        <div className="mb-5 flex items-center gap-2 border-b border-[var(--border)] pb-4">
          <LayoutDashboard className="h-4 w-4 text-[var(--brand)]" />
          <h2 className="text-sm font-semibold">看板配置</h2>
        </div>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (!canSubmit || createDashboard.isPending) return;
            createDashboard.mutate(
              { name: name.trim(), range, description: desc.trim() || undefined },
              { onSuccess: () => navigate('/admin/metrics'), onError: () => navigate('/admin/metrics') },
            );
          }}
        >
          <div>
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">看板名称</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="例如 高优客户体验" className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
          </div>
          <div>
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">默认时间范围</label>
            <select value={range} onChange={(e) => setRange(e.target.value as MetricsTimeRange)} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]">
              {TIME_RANGES.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
            </select>
          </div>
          <div>
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">描述</label>
            <textarea value={desc} onChange={(e) => setDesc(e.target.value)} rows={3} placeholder="可选" className="mt-1.5 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 py-2 text-sm outline-none focus:border-[var(--brand)]" />
          </div>
          <div className="flex justify-end gap-2 border-t border-[var(--border)] pt-5">
            <Link to="/admin/metrics" className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold">取消</Link>
            <button type="submit" disabled={!canSubmit || createDashboard.isPending} className="rounded-xl bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white disabled:opacity-40">创建</button>
          </div>
        </form>
      </section>
    </div>
  );
}
