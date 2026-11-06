/**
 * 新建告警规则 — 独立页面 /admin/quotas/alerts/new
 */
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, Bell } from 'lucide-react';
import type { AlertRule, AlertSeverity } from './schema';
import { useCreateAlert } from './useQuotas';
import { SEVERITY_BADGE } from './components/constants';
import { AdminPage } from '@/components/feedback/AdminPage';

export default function AlertCreatePage() {
  const navigate = useNavigate();
  const createAlert = useCreateAlert();
  const [name, setName] = useState('');
  const [scope, setScope] = useState<AlertRule['scope']>('enterprise');
  const [severity, setSeverity] = useState<AlertSeverity>('warning');
  const [metric, setMetric] = useState('月度 Token');
  const [threshold, setThreshold] = useState(80);
  const [cooldown, setCooldown] = useState('12h');
  const [notify, setNotify] = useState('admin@');
  const canSubmit = name.trim().length > 0 && !createAlert.isPending;

  return (
    <AdminPage density="lg">
      <Link to="/admin/quotas" className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--brand)]">
        <ArrowLeft className="h-3.5 w-3.5" />返回额度管理
      </Link>
      <header>
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--brand)]">额度管理</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">新建告警规则</h1>
        <p className="mt-2 max-w-2xl text-sm text-[var(--text-muted)]">为额度使用配置告警阈值与通知渠道。</p>
      </header>
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6">
        <div className="mb-5 flex items-center gap-2 border-b border-[var(--border)] pb-4">
          <Bell className="h-4 w-4 text-[var(--brand)]" />
          <h2 className="text-sm font-semibold">规则配置</h2>
        </div>
        <form
          className="grid gap-4 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!canSubmit) return;
            createAlert.mutate(
              { name: name.trim(), scope, severity, metric, threshold, cooldown, notify },
              { onSuccess: () => navigate('/admin/quotas'), onError: () => navigate('/admin/quotas') },
            );
          }}
        >
          <div className="sm:col-span-2">
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">规则名称</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="例如:部门使用率告警" className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
          </div>
          <div>
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">范围</label>
            <select value={scope} onChange={(e) => setScope(e.target.value as AlertRule['scope'])} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]">
              <option value="enterprise">企业</option>
              <option value="department">部门</option>
              <option value="channel">渠道</option>
            </select>
          </div>
          <div>
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">严重度</label>
            <select value={severity} onChange={(e) => setSeverity(e.target.value as AlertSeverity)} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]">
              {(Object.keys(SEVERITY_BADGE) as AlertSeverity[]).map((s) => <option key={s} value={s}>{SEVERITY_BADGE[s].label}</option>)}
            </select>
          </div>
          <div>
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">指标</label>
            <input value={metric} onChange={(e) => setMetric(e.target.value)} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
          </div>
          <div>
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">阈值</label>
            <input type="number" value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
          </div>
          <div>
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">静默时长</label>
            <input value={cooldown} onChange={(e) => setCooldown(e.target.value)} placeholder="例如:12h" className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
          </div>
          <div>
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">通知人</label>
            <input value={notify} onChange={(e) => setNotify(e.target.value)} placeholder="邮箱,逗号分隔" className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
          </div>
          <div className="sm:col-span-2 flex justify-end gap-2 border-t border-[var(--border)] pt-5">
            <Link to="/admin/quotas" className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold">取消</Link>
            <button type="submit" disabled={!canSubmit} className="rounded-xl bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white disabled:opacity-40">创建规则</button>
          </div>
        </form>
      </section>
    </AdminPage>
  );
}
