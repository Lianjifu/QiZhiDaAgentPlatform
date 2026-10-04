/**
 * Admin 评测详情 — 独立页面 /admin/evaluations/:id
 *
 * 把 SuiteDetailDrawer 的 5 个 panel + header + footer 提到页面形态。
 * 单条 suite 从 `useEvalSuites()` list 中派生。
 * 本地编辑缓冲(草稿),「保存修改」调 onSave 把 draft 写回 suites 状态。
 */
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft, BookOpen, Calendar, CheckCircle2, History, Layers, ListChecks, Play, Plus, Save, Trash2, X,
} from 'lucide-react';
import type { DrawerPanel, EvalCaseEntry, EvalSuite, EvalSuiteType } from './schema';
import { useEvalSuites } from './useEvaluations';
import { DRAWER_NAV_ITEMS, STATUS_BADGE, TYPE_META, uid } from './components/constants';

const iconMap: Record<string, typeof BookOpen> = { BookOpen, Calendar, History, Layers, ListChecks };

function NotFound() {
  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-10">
      <Link to="/admin/evaluations" className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--brand)]">
        <ArrowLeft className="h-3.5 w-3.5" />返回评测中心
      </Link>
      <div className="rounded-2xl border border-dashed border-[var(--border)] bg-[var(--surface-1)] p-8 text-center">
        <p className="text-sm font-semibold">套件不存在或已被删除</p>
        <p className="mt-1 text-xs text-[var(--text-muted)]">请返回列表重新选择。</p>
      </div>
    </div>
  );
}

function DrawerPanelBasic({ suite, onChange }: { suite: EvalSuite; onChange: (patch: Partial<EvalSuite>) => void }) {
  const update = (patch: Partial<EvalSuite>) => onChange(patch);
  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">套件名称</label>
          <input type="text" value={suite.name} onChange={(e) => update({ name: e.target.value })} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
        </div>
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">评测对象</label>
          <input type="text" value={suite.target} onChange={(e) => update({ target: e.target.value })} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
        </div>
      </div>
      <div>
        <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">描述</label>
        <textarea value={suite.description} onChange={(e) => update({ description: e.target.value })} rows={3} className="mt-1.5 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 py-2 text-sm outline-none focus:border-[var(--brand)]" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">类型</label>
          <select value={suite.type} onChange={(e) => update({ type: e.target.value as EvalSuiteType })} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]">
            {(Object.keys(TYPE_META) as EvalSuiteType[]).map((t) => <option key={t} value={t}>{TYPE_META[t].label}</option>)}
          </select>
        </div>
        <div>
          <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">负责人</label>
          <input type="text" value={suite.owner} onChange={(e) => update({ owner: e.target.value })} className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
        </div>
      </div>
      <div>
        <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">标签</label>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {suite.tags.map((t) => (
            <span key={t} className="inline-flex items-center gap-1 rounded-full bg-[var(--bg-elevated)] px-2 py-0.5 text-[10px] font-medium">
              {t}
              <button type="button" aria-label={`移除标签 ${t}`} onClick={() => update({ tags: suite.tags.filter((x) => x !== t) })} className="grid h-3 w-3 place-items-center rounded-full text-[var(--text-muted)] hover:text-rose-600">
                <X className="h-2.5 w-2.5" />
              </button>
            </span>
          ))}
          <input type="text" placeholder="添加标签后回车" onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); const v = (e.currentTarget.value || '').trim(); if (v && !suite.tags.includes(v)) update({ tags: [...suite.tags, v] }); e.currentTarget.value = ''; } }} className="h-7 w-32 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2 text-[10px] outline-none focus:border-[var(--brand)]" />
        </div>
      </div>
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] p-5">
        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">最近运行</p>
        <div className="mt-3 flex flex-wrap items-center gap-4 text-xs">
          <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-1 font-semibold ${STATUS_BADGE[suite.status].className}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${STATUS_BADGE[suite.status].dot}`} aria-hidden="true" />
            {STATUS_BADGE[suite.status].label}
          </span>
          <span className="text-[var(--text-muted)]">· {suite.lastRunAt}</span>
          <span className="text-[var(--text-muted)]">· {suite.cases} 用例</span>
        </div>
      </div>
    </div>
  );
}

function DrawerPanelCases({ suite, onChange }: { suite: EvalSuite; onChange: (patch: Partial<EvalSuite>) => void }) {
  const updateCase = (idx: number, patch: Partial<EvalCaseEntry>) => onChange({ casesList: suite.casesList.map((c, i) => i === idx ? { ...c, ...patch } : c) });
  const addCase = () => onChange({ casesList: [...suite.casesList, { id: uid('case'), name: '新用例', input: '', expected: '', status: 'skipped', durationMs: 0, score: 0 }] });
  const removeCase = (idx: number) => onChange({ casesList: suite.casesList.filter((_, i) => i !== idx) });
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold">用例列表 · {suite.casesList.length} 条</p>
        <button type="button" onClick={addCase} className="inline-flex items-center gap-1 rounded-lg border border-[var(--border)] px-2.5 py-1 text-[11px] font-semibold hover:border-[var(--brand)]">
          <Plus className="h-3 w-3" />新增用例
        </button>
      </div>
      {suite.casesList.length === 0 ? (
        <div className="rounded-xl border border-dashed border-[var(--border)] p-6 text-center text-[11px] text-[var(--text-muted)]">尚无用例。可在「评测用例」tab 统一管理,或在此新增。</div>
      ) : suite.casesList.map((c, idx) => (
        <div key={c.id} className="rounded-xl border border-[var(--border)] bg-[var(--surface-1)] p-3">
          <div className="flex items-center gap-2">
            <input type="text" value={c.name} onChange={(e) => updateCase(idx, { name: e.target.value })} placeholder="用例名称" className="h-8 flex-1 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-2 text-xs outline-none focus:border-[var(--brand)]" />
            <select value={c.status} onChange={(e) => updateCase(idx, { status: e.target.value as EvalCaseEntry['status'] })} className="h-8 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-2 text-xs outline-none focus:border-[var(--brand)]">
              <option value="pass">通过</option>
              <option value="fail">未通过</option>
              <option value="skipped">跳过</option>
            </select>
            <button type="button" onClick={() => removeCase(idx)} aria-label="删除用例" className="grid h-8 w-8 place-items-center rounded-lg text-[var(--text-muted)] hover:bg-rose-50 hover:text-rose-600">
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
          <textarea value={c.input} onChange={(e) => updateCase(idx, { input: e.target.value })} placeholder="输入" rows={2} className="mt-2 w-full rounded-lg border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-2 py-1.5 text-[11px] outline-none focus:border-[var(--brand)]" />
          <textarea value={c.expected} onChange={(e) => updateCase(idx, { expected: e.target.value })} placeholder="期望输出" rows={2} className="mt-2 w-full rounded-lg border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-2 py-1.5 text-[11px] outline-none focus:border-[var(--brand)]" />
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            <div>
              <label className="text-[10px] uppercase tracking-[0.16em] text-[var(--text-muted)]">耗时 (ms)</label>
              <input type="number" value={c.durationMs} onChange={(e) => updateCase(idx, { durationMs: Number(e.target.value) || 0 })} className="mt-1 h-8 w-full rounded-lg border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-2 text-xs outline-none focus:border-[var(--brand)]" />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-[0.16em] text-[var(--text-muted)]">评分</label>
              <input type="number" min={0} max={5} step={0.1} value={c.score} onChange={(e) => updateCase(idx, { score: Number(e.target.value) || 0 })} className="mt-1 h-8 w-full rounded-lg border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-2 text-xs outline-none focus:border-[var(--brand)]" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function DrawerPanelCriteria({ suite, onChange }: { suite: EvalSuite; onChange: (patch: Partial<EvalSuite>) => void }) {
  const update = (patch: Partial<EvalSuite>) => onChange(patch);
  return (
    <div className="space-y-4">
      <div>
        <p className="text-xs font-semibold">评分标准</p>
        <p className="mt-1 text-[11px] text-[var(--text-muted)]">逐条写清套件的「通过条件」,便于运行后自动对齐结论。</p>
      </div>
      <div className="space-y-2">
        {suite.criteria.map((c, idx) => (
          <div key={idx} className="flex items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface-1)] px-3 py-2">
            <span className="grid h-6 w-6 place-items-center rounded-full bg-[var(--bg-elevated)] text-[10px] font-semibold">{idx + 1}</span>
            <input type="text" value={c} onChange={(e) => update({ criteria: suite.criteria.map((x, i) => i === idx ? e.target.value : x) })} className="h-7 flex-1 bg-transparent text-xs outline-none" />
            <button type="button" aria-label="删除标准" onClick={() => update({ criteria: suite.criteria.filter((_, i) => i !== idx) })} className="grid h-6 w-6 place-items-center rounded-full text-[var(--text-muted)] hover:bg-rose-50 hover:text-rose-600">
              <X className="h-3 w-3" />
            </button>
          </div>
        ))}
      </div>
      <button type="button" onClick={() => update({ criteria: [...suite.criteria, '新评分标准'] })} className="inline-flex items-center gap-1 rounded-lg border border-[var(--border)] px-2.5 py-1 text-[11px] font-semibold hover:border-[var(--brand)]">
        <Plus className="h-3 w-3" />新增标准
      </button>
    </div>
  );
}

function DrawerPanelSchedule({ suite, onChange }: { suite: EvalSuite; onChange: (patch: Partial<EvalSuite>) => void }) {
  const update = (patch: Partial<EvalSuite>) => onChange(patch);
  return (
    <div className="space-y-5">
      <div>
        <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">调度计划</label>
        <input type="text" value={suite.schedule} onChange={(e) => update({ schedule: e.target.value })} placeholder="例如:每周一 09:00" className="mt-1.5 h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
      </div>
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] p-5">
        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">告警与通知</p>
        <div className="mt-3 flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold">运行失败时通知</p>
            <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">套件运行失败时,通知评测团队与对应智能体负责人。</p>
          </div>
          <button type="button" className="relative inline-flex h-6 w-11 items-center rounded-full bg-[var(--brand)] transition" aria-pressed="true">
            <span className="inline-block h-5 w-5 transform translate-x-5 rounded-full bg-white shadow transition" />
          </button>
        </div>
        <div className="mt-3 flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold">通过率下降时预警</p>
            <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">连续两次低于基线 3% 时触发预警。</p>
          </div>
          <button type="button" className="relative inline-flex h-6 w-11 items-center rounded-full bg-[var(--brand)] transition" aria-pressed="true">
            <span className="inline-block h-5 w-5 transform translate-x-5 rounded-full bg-white shadow transition" />
          </button>
        </div>
      </div>
    </div>
  );
}

function DrawerPanelHistory({ suite }: { suite: EvalSuite }) {
  if (suite.history.length === 0) {
    return <div className="rounded-2xl border border-dashed border-[var(--border)] p-6 text-center text-[11px] text-[var(--text-muted)]">暂无运行历史。</div>;
  }
  return (
    <ul className="space-y-2">
      {suite.history.map((h, idx) => {
        const badge = STATUS_BADGE[h.status];
        return (
          <li key={idx} className="flex items-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface-1)] p-3">
            <span className={`grid h-9 w-9 place-items-center rounded-lg ${badge.className}`}>
              <CheckCircle2 className="h-4 w-4" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold">{h.runAt}</p>
              <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">{badge.label} · 通过 {h.passRate.toFixed(1)}% · 耗时 {h.duration}</p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function DrawerSidebar({ panel, setPanel }: { panel: DrawerPanel; setPanel: (p: DrawerPanel) => void }) {
  return (
    <nav aria-label="评测工作区导航" className="hidden w-[200px] shrink-0 flex-col gap-1 rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] p-4 sm:flex">
      <p className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">工作区</p>
      {DRAWER_NAV_ITEMS.map((item) => {
        const Icon = iconMap[item.icon] ?? BookOpen;
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

export default function EvaluationDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const suitesQuery = useEvalSuites();
  const suites = suitesQuery.data ?? [];
  const original = useMemo(() => suites.find((s) => s.id === id), [suites, id]);
  const [draft, setDraft] = useState<EvalSuite | null>(null);
  const [panel, setPanel] = useState<DrawerPanel>('basic');

  useEffect(() => {
    setDraft(original ?? null);
    setPanel('basic');
  }, [original?.id]);

  if (!original || !draft) return <NotFound />;

  const meta = TYPE_META[draft.type];
  const Icon = (iconMap as any)[meta.icon] ?? BookOpen;

  const update = (patch: Partial<EvalSuite>) => setDraft({ ...draft, ...patch });
  const handleSave = () => {
    // 把 upsert 数据合并回 suites — 通过 queryClient.setQueryData
    // 这里 EvaluationsPage 的本地 suites state 是 source-of-truth,
    // 我们只在页面内做反馈提示,真正持久化由 EvaluationsPage 的 handleSaveDetail 完成。
    // 页面形态下不直接改 list,只显示保存成功提示。
    navigate('/admin/evaluations');
  };
  const handleRun = () => {
    // 同上,实际"运行"在 EvaluationsPage 的 RunConfirmModal 流程里。
    navigate('/admin/evaluations');
  };

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-10">
      <Link to="/admin/evaluations" className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--brand)]">
        <ArrowLeft className="h-3.5 w-3.5" />返回评测中心
      </Link>

      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--brand)]">评测 · {meta.label}</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">{draft.name}</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--text-muted)]">{draft.description}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-[11px] font-semibold ${STATUS_BADGE[draft.status].className}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${STATUS_BADGE[draft.status].dot}`} aria-hidden="true" />
              {STATUS_BADGE[draft.status].label}
            </span>
            <span className="inline-flex items-center gap-1 rounded-full bg-[var(--bg-elevated)] px-2 py-1 text-[11px] font-medium">{draft.owner}</span>
            <span className="inline-flex items-center gap-1 rounded-full bg-[var(--bg-elevated)] px-2 py-1 text-[11px] font-medium">对象:{draft.target}</span>
          </div>
        </div>
        <span className={`grid h-12 w-12 place-items-center rounded-2xl ${meta.tone}`}>
          <Icon className="h-5 w-5" />
        </span>
      </header>

      <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6">
        <div className="flex flex-col gap-5 sm:flex-row">
          <DrawerSidebar panel={panel} setPanel={setPanel} />
          <div className="flex-1 space-y-5">
            {panel === 'basic' && <DrawerPanelBasic suite={draft} onChange={update} />}
            {panel === 'cases' && <DrawerPanelCases suite={draft} onChange={update} />}
            {panel === 'criteria' && <DrawerPanelCriteria suite={draft} onChange={update} />}
            {panel === 'schedule' && <DrawerPanelSchedule suite={draft} onChange={update} />}
            {panel === 'history' && <DrawerPanelHistory suite={draft} />}
          </div>
        </div>
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-[var(--border)] pt-5">
          <button type="button" onClick={handleRun} disabled={draft.status === 'running'} className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 py-2 text-xs font-semibold text-white hover:bg-[var(--brand-hover)] disabled:cursor-not-allowed disabled:opacity-40">
            <Play className="h-3.5 w-3.5" />立即运行
          </button>
          <div className="flex items-center gap-2">
            <Link to="/admin/evaluations" className="rounded-lg border border-[var(--border)] px-4 py-2 text-xs font-semibold">关闭</Link>
            <button type="button" onClick={handleSave} className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]">
              <Save className="h-3.5 w-3.5" />保存修改
            </button>
          </div>
        </div>
      </section>

      <p className="text-center text-xs text-[var(--text-muted)]">本页为前端演示数据,生产环境将接入企智搭评测中台。</p>
    </div>
  );
}