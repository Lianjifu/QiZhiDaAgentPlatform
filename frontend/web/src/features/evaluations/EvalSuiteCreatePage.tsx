/**
 * 新建评测套件 — 独立页面 /admin/evaluations/new
 */
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, Plus } from 'lucide-react';
import type { EvalSuiteType } from './schema';
import { TYPE_META } from './components/constants';
import { StepIndicator } from './components/Primitives';
import { useCreateEvalSuite } from './useEvaluations';

export default function EvalSuiteCreatePage() {
  const navigate = useNavigate();
  const createSuite = useCreateEvalSuite();
  const [step, setStep] = useState(1);
  const [name, setName] = useState('');
  const [type, setType] = useState<EvalSuiteType>('capability');
  const [target, setTarget] = useState('');
  const [description, setDescription] = useState('');
  const [owner, setOwner] = useState('张敏');
  const [schedule, setSchedule] = useState('每周一 09:00');
  const [criteriaText, setCriteriaText] = useState('意图分类准确率 ≥ 95%\n工具调用成功率 ≥ 90%');
  const canNext1 = name.trim().length > 0 && target.trim().length > 0;

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-10">
      <Link to="/admin/evaluations" className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--brand)]">
        <ArrowLeft className="h-3.5 w-3.5" />返回评测中心
      </Link>
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--brand)]">评测中心</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">新建评测套件</h1>
        </div>
        <p className="max-w-sm text-xs leading-5 text-[var(--text-muted)]">
          {step === 1 ? '设置套件基本信息与评测对象' : step === 2 ? '设定调度计划与评分标准' : '确认后将以「排队中」状态加入列表'}
        </p>
      </header>
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6">
        <div className="mb-5 flex items-center gap-2 border-b border-[var(--border)] pb-4">
          <Plus className="h-4 w-4 text-[var(--brand)]" />
          <h2 className="text-sm font-semibold">{['基本信息', '调度与标准', '确认'][step - 1]}</h2>
        </div>
        <div className="mb-5"><StepIndicator current={step} total={3} labels={['基本信息', '调度与标准', '确认']} /></div>
        {step === 1 && (
          <div className="space-y-4">
            <div>
              <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">套件名称</label>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="例如:客户沟通能力评测" className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">类型</label>
                <select value={type} onChange={(e) => setType(e.target.value as EvalSuiteType)} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]">
                  {(Object.keys(TYPE_META) as EvalSuiteType[]).map((t) => <option key={t} value={t}>{TYPE_META[t].label}</option>)}
                </select>
              </div>
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">评测对象</label>
                <input value={target} onChange={(e) => setTarget(e.target.value)} placeholder="例如:客户沟通助手" className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
              </div>
            </div>
            <div>
              <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">负责人</label>
              <input value={owner} onChange={(e) => setOwner(e.target.value)} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
            </div>
            <div>
              <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">描述</label>
              <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} placeholder="用一两句话说明套件目标" className="mt-1.5 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 py-2 text-sm outline-none focus:border-[var(--brand)]" />
            </div>
          </div>
        )}
        {step === 2 && (
          <div className="space-y-4">
            <div>
              <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">调度计划</label>
              <input value={schedule} onChange={(e) => setSchedule(e.target.value)} placeholder="例如:每周一 09:00" className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
            </div>
            <div>
              <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">评分标准 (每行一条)</label>
              <textarea value={criteriaText} onChange={(e) => setCriteriaText(e.target.value)} rows={6} className="mt-1.5 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 py-2 text-xs leading-6 outline-none focus:border-[var(--brand)]" />
            </div>
          </div>
        )}
        {step === 3 && (
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] p-5 text-xs">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">确认信息</p>
            <ul className="mt-3 space-y-1">
              <li>· 名称:<span className="font-semibold">{name}</span></li>
              <li>· 类型:{TYPE_META[type].label}</li>
              <li>· 评测对象:<span className="font-semibold">{target}</span></li>
              <li>· 负责人:{owner}</li>
              <li>· 调度:{schedule}</li>
              <li>· 评分标准:{criteriaText.split('\n').filter(Boolean).length} 条</li>
              <li>· 描述:{description.trim() || '新创建的评测套件'}</li>
            </ul>
          </div>
        )}
        <div className="mt-6 flex flex-wrap items-center justify-end gap-2 border-t border-[var(--border)] pt-5">
          {step > 1 && <button type="button" onClick={() => setStep((s) => s - 1)} className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold">上一步</button>}
          <Link to="/admin/evaluations" className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold">取消</Link>
          {step < 3 && <button type="button" onClick={() => setStep((s) => s + 1)} disabled={step === 1 && !canNext1} className="rounded-xl bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white disabled:opacity-40">下一步</button>}
          {step === 3 && <button type="button" onClick={() => createSuite.mutate(
            { name: name.trim(), type, target: target.trim(), owner, description: description.trim() || '新创建的评测套件', schedule, criteria: criteriaText.split('\n').filter(Boolean) },
            { onSuccess: () => navigate('/admin/evaluations'), onError: () => navigate('/admin/evaluations') },
          )} disabled={createSuite.isPending} className="rounded-xl bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white disabled:opacity-40">创建套件</button>}
        </div>
      </section>
    </div>
  );
}
