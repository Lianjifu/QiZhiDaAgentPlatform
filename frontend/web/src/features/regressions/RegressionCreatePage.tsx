/**
 * Admin 新建回归追踪 — 独立页面 /admin/regressions/new
 *
 * 把 CreateTrackModal 的 3 步表单搬到页面形态;
 * 复用 RegressionDetailPage 一样的 wrapper + 返回 Link + header;
 * 提交成功 navigate('/admin/regressions')。
 */
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { GitBranch } from 'lucide-react';
import { StepIndicator } from './components/Primitives';
import { useCreateRegressionTrack } from './useRegressions';

export default function RegressionCreatePage() {
  const navigate = useNavigate();
  const createTrack = useCreateRegressionTrack();
  const [step, setStep] = useState(1);
  const [name, setName] = useState('');
  const [agent, setAgent] = useState('');
  const [owner, setOwner] = useState('张敏');
  const [baseline, setBaseline] = useState('v1.0');
  const [current, setCurrent] = useState('v1.1');
  const [schedule, setSchedule] = useState('每次发布后');
  const [notes, setNotes] = useState('');

  const canNext = name.trim().length > 0 && agent.trim().length > 0;
  const handleCreate = () => {
    createTrack.mutate(
      {
        name: name.trim(),
        agent: agent.trim(),
        owner,
        baselineVersion: baseline,
        currentVersion: current,
        schedule,
        notes: notes.trim() || '新创建的回归追踪',
      },
      { onSuccess: () => navigate('/admin/regressions'), onError: () => navigate('/admin/regressions') },
    );
  };

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-10">
      <Link to="/admin/regressions" className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--brand)]">
        <span aria-hidden="true">←</span>返回回归追踪
      </Link>

      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--brand)]">回归追踪</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">新建追踪</h1>
        </div>
        <p className="max-w-sm text-xs leading-5 text-[var(--text-muted)]">
          {step === 1 ? '追踪基本信息与对象' : step === 2 ? '选择基线版本与调度' : '确认后将以「稳定」状态加入列表'}
        </p>
      </header>

      <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6">
        <div className="mb-5 flex items-center gap-2 border-b border-[var(--border)] pb-4">
          <GitBranch className="h-4 w-4 text-[var(--brand)]" />
          <h2 className="text-sm font-semibold">{step === 1 ? '基本信息' : step === 2 ? '基线与调度' : '确认信息'}</h2>
        </div>
        <div className="mb-5">
          <StepIndicator current={step} total={3} labels={['基本信息', '基线与调度', '确认']} />
        </div>

        {step === 1 && (
          <div className="space-y-4">
            <div>
              <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">追踪名称</label>
              <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="例如:客户沟通助手回归追踪" className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">追踪对象</label>
                <input type="text" value={agent} onChange={(e) => setAgent(e.target.value)} placeholder="例如:客户沟通助手" className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
              </div>
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">负责人</label>
                <input type="text" value={owner} onChange={(e) => setOwner(e.target.value)} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
              </div>
            </div>
            <div>
              <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">说明</label>
              <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} className="mt-1.5 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 py-2 text-sm outline-none focus:border-[var(--brand)]" />
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">基线版本</label>
                <input type="text" value={baseline} onChange={(e) => setBaseline(e.target.value)} placeholder="v1.0" className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
              </div>
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">当前版本</label>
                <input type="text" value={current} onChange={(e) => setCurrent(e.target.value)} placeholder="v1.1" className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
              </div>
            </div>
            <div>
              <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">调度</label>
              <input type="text" value={schedule} onChange={(e) => setSchedule(e.target.value)} placeholder="每次发布后 / 每日 23:00" className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] p-5 text-xs">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">确认信息</p>
            <ul className="mt-3 space-y-1">
              <li>· 名称:<span className="font-semibold">{name}</span></li>
              <li>· 对象:<span className="font-semibold">{agent}</span></li>
              <li>· 负责人:{owner}</li>
              <li>· 基线:{baseline} · 当前:{current}</li>
              <li>· 调度:{schedule}</li>
            </ul>
          </div>
        )}

        <div className="mt-6 flex flex-wrap items-center justify-end gap-2 border-t border-[var(--border)] pt-5">
          {step > 1 && <button type="button" onClick={() => setStep((s) => Math.max(1, s - 1))} className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold">上一步</button>}
          <Link to="/admin/regressions" className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold">取消</Link>
          {step < 3 && <button type="button" onClick={() => setStep((s) => s + 1)} disabled={step === 1 && !canNext} className="rounded-xl bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40">下一步</button>}
          {step === 3 && <button type="button" onClick={handleCreate} disabled={createTrack.isPending} className="rounded-xl bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white disabled:opacity-40">创建追踪</button>}
        </div>
      </section>
    </div>
  );
}