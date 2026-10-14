/**
 * 新建工作流 — 独立页面 /admin/workflows/new
 *
 * 顶部返回按钮回 /admin/workflows;主区域左 1/3 纵向 stepper,右 2/3 工作区。
 * 3 步(基本信息 / 选模板 / 确认)完成后调 useCreateWorkflow,
 * 然后导航到 /admin/workflows/:newId?edit=1 进入画布。
 */
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AlertCircle, ArrowLeft, ArrowRight, FileCheck2, History, Info, Sparkles, Wand2 } from 'lucide-react';
import { NoticeBanner } from '@/components/feedback/NoticeBanner';
import { useCreateWorkflow } from './useWorkflows';
import { normalizeError } from '@/api/shared/http-error';
import type { Flow, TriggerType } from './schema';
import { TEMPLATE_CHOICES, TRIGGER_BADGE, TRIGGERS, uid } from './components/constants';

type StepKey = 'basic' | 'template' | 'review';
interface StepDef {
  key: StepKey;
  index: 1 | 2 | 3;
  title: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
}

const STEPS: StepDef[] = [
  { key: 'basic', index: 1, title: '基本信息', description: '命名、描述与触发方式', icon: Wand2 },
  { key: 'template', index: 2, title: '选模板', description: '从预设开始或留白', icon: Sparkles },
  { key: 'review', index: 3, title: '确认创建', description: '核对信息后写入工作台', icon: FileCheck2 },
];

const TEMPLATE_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  Workflow: ({ className }) => <span className={className}>⊟</span>,
  AlertCircle,
  Sparkles,
  History,
};

export default function WorkflowCreatePage() {
  const navigate = useNavigate();
  const createWorkflow = useCreateWorkflow();
  const [step, setStep] = useState<1 | 2 | 3>(1);

  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [trigger, setTrigger] = useState<TriggerType>('消息触发');
  const [template, setTemplate] = useState<string>('blank');
  const [notice, setNotice] = useState('');

  const canNext = step === 1 ? name.trim().length > 0 : true;

  const handleSubmit = () => {
    const id = uid('wf');
    const flow: Flow = {
      id,
      name: name.trim() || '未命名工作流',
      description: desc.trim() || '尚未填写描述',
      owner: '当前管理员',
      scene: '团队协作',
      trigger,
      status: 'draft',
      callCount: 0,
      inputs: 1,
      outputs: 1,
      createdAt: '今天',
      updatedAt: '刚刚',
      boundAgents: [],
      versions: [{ v: 'v0.1-草稿', at: '刚刚', operator: '当前管理员', note: '新建工作流' }],
      initialNodes: [
        { id: 'n-trigger', type: 'flowNode', position: { x: 40, y: 120 }, data: { label: trigger, subtitle: '工作流入口', kind: 'trigger', config: { trigger } } },
      ],
      initialEdges: [],
    };
    createWorkflow.mutate(flow, {
      onSuccess: (created) => {
        navigate(`/admin/workflows/${created.id}?edit=1`);
      },
      onError: (cause) => setNotice(`创建失败：${normalizeError(cause).message}`),
    });
  };

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-6">
      <Link
        to="/admin/workflows"
        className="inline-flex w-fit items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-medium text-[var(--text-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--brand)]"
      >
        <ArrowLeft className="h-3.5 w-3.5" />返回工作流管理
      </Link>

      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-700 dark:text-amber-300">ADMIN / 工作流管理</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">新建工作流</h1>
        </div>
        <p className="max-w-sm text-xs leading-5 text-[var(--text-muted)]">
          跟随向导完成 3 个步骤 — 命名、模板与确认。创建后将自动进入画布继续编排节点。
        </p>
      </header>

      {notice && (
        <NoticeBanner tone="amber" onClose={() => setNotice('')}>
          {notice}
        </NoticeBanner>
      )}

      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        <aside aria-label="创建步骤" className="lg:sticky lg:top-5 lg:self-start">
          <ol className="relative space-y-1">
            {STEPS.map((s) => {
              const active = step === s.index;
              const done = step > s.index;
              const Icon = s.icon;
              return (
                <li key={s.key} className="relative">
                  <button
                    type="button"
                    onClick={() => setStep(s.index)}
                    aria-current={active ? 'step' : undefined}
                    className={`flex w-full items-start gap-3 rounded-xl px-3 py-3 text-left transition ${
                      active
                        ? 'bg-[var(--brand-light)]'
                        : 'hover:bg-[var(--bg-hover)]'
                    }`}
                  >
                    <span
                      className={`grid h-10 w-10 shrink-0 place-items-center rounded-full border-2 transition ${
                        done
                          ? 'border-[var(--brand)] bg-[var(--brand)] text-white'
                          : active
                            ? 'border-[var(--brand)] bg-[var(--surface-1)] text-[var(--brand)]'
                            : 'border-[var(--border)] bg-[var(--surface-1)] text-[var(--text-muted)]'
                      }`}
                    >
                      <Icon className="h-4 w-4" />
                    </span>
                    <span className="min-w-0 flex-1 pt-0.5">
                      <span className="flex items-center gap-1.5">
                        <span className={`text-[11px] font-semibold uppercase tracking-wide ${active ? 'text-[var(--brand)]' : 'text-[var(--text-muted)]'}`}>
                          第 {s.index} 步
                        </span>
                      </span>
                      <span className={`mt-0.5 block text-sm font-semibold ${active ? 'text-[var(--text)]' : 'text-[var(--text-secondary)]'}`}>
                        {s.title}
                      </span>
                      <span className="mt-0.5 block text-[11px] leading-4 text-[var(--text-muted)]">
                        {s.description}
                      </span>
                    </span>
                    {active && <ArrowRight className="mt-3 h-3.5 w-3.5 shrink-0 text-[var(--brand)]" />}
                  </button>
                </li>
              );
            })}
          </ol>

          <div className="mt-2 flex items-start gap-2 rounded-xl border border-dashed border-[var(--border)] p-3 text-[11px] leading-4 text-[var(--text-muted)]">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--brand)]" />
            <span>
              草稿状态可随时修改,所有节点与连接可在画布中继续编排。
            </span>
          </div>
        </aside>

        <section
          aria-labelledby="create-step-title"
          className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6"
        >
          <div className="mb-5 flex items-center justify-between border-b border-[var(--border)] pb-4">
            <h2 id="create-step-title" className="text-sm font-semibold">
              {STEPS.find((s) => s.index === step)?.title}
            </h2>
            <span className="text-[11px] font-medium tabular-nums text-[var(--text-muted)]">
              {step} / 3
            </span>
          </div>

          {step === 1 && (
            <div className="space-y-4">
              <label className="block">
                <span className="text-xs font-semibold text-[var(--text-secondary)]">工作流名称</span>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="例如:客户投诉自动分流"
                  className="mt-2 h-10 w-full rounded-xl border border-[var(--border)] bg-[var(--surface-1)] px-3 text-sm outline-none focus:border-[var(--brand)]"
                />
              </label>
              <label className="block">
                <span className="text-xs font-semibold text-[var(--text-secondary)]">描述</span>
                <textarea
                  value={desc}
                  onChange={(e) => setDesc(e.target.value)}
                  rows={3}
                  placeholder="简要说明这个工作流解决什么问题"
                  className="mt-2 w-full rounded-xl border border-[var(--border)] bg-[var(--surface-1)] px-3 py-2 text-sm outline-none focus:border-[var(--brand)]"
                />
              </label>
              <div>
                <span className="text-xs font-semibold text-[var(--text-secondary)]">触发器类型</span>
                <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
                  {TRIGGERS.map((t) => {
                    const Icon = TRIGGER_BADGE[t].icon;
                    return (
                      <button
                        key={t}
                        type="button"
                        onClick={() => setTrigger(t)}
                        aria-pressed={trigger === t}
                        className={`rounded-xl border p-3 text-left transition ${trigger === t ? 'border-[var(--brand)] bg-[var(--brand-light)]' : 'border-[var(--border)] hover:border-[var(--brand)]'}`}
                      >
                        <Icon className="h-4 w-4 text-[var(--brand)]" />
                        <p className="mt-2 text-xs font-semibold">{TRIGGER_BADGE[t].label}</p>
                        <p className="text-[10px] text-[var(--text-muted)]">{t}</p>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="grid grid-cols-2 gap-3">
              {TEMPLATE_CHOICES.map((tpl) => {
                const Icon = TEMPLATE_ICONS[tpl.icon] ?? Sparkles;
                return (
                  <button
                    key={tpl.id}
                    type="button"
                    onClick={() => setTemplate(tpl.id)}
                    aria-pressed={template === tpl.id}
                    className={`rounded-2xl border p-4 text-left transition ${template === tpl.id ? 'border-[var(--brand)] bg-[var(--brand-light)]' : 'border-[var(--border)] hover:border-[var(--brand)]'}`}
                  >
                    <span className="grid h-9 w-9 place-items-center rounded-lg bg-[var(--bg-elevated)]">
                      <Icon className="h-4 w-4 text-[var(--brand)]" />
                    </span>
                    <p className="mt-3 text-sm font-semibold">{tpl.name}</p>
                    <p className="mt-1 text-[11px] text-[var(--text-muted)]">{tpl.desc}</p>
                  </button>
                );
              })}
            </div>
          )}

          {step === 3 && (
            <div className="space-y-4">
              <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] p-5">
                <p className="text-xs text-[var(--text-muted)]">已准备好以下工作流</p>
                <p className="mt-2 text-base font-semibold">{name.trim() || '未命名工作流'}</p>
                <p className="mt-1 text-xs text-[var(--text-muted)]">{desc.trim() || '尚未填写描述'}</p>
                <div className="mt-3 flex flex-wrap gap-2 text-[10px]">
                  <span className={`inline-flex items-center gap-1 rounded-full px-2 py-1 font-semibold ${TRIGGER_BADGE[trigger].className}`}>
                    {(() => { const Icon = TRIGGER_BADGE[trigger].icon; return <Icon className="h-3 w-3" />; })()}触发器: {trigger}
                  </span>
                  <span className="inline-flex items-center gap-1 rounded-full bg-[var(--surface-1)] px-2 py-1 font-semibold text-[var(--text-secondary)]">模板: {TEMPLATE_CHOICES.find((t) => t.id === template)?.name}</span>
                </div>
              </div>
              <div className="flex items-start gap-2 rounded-xl border border-dashed border-[var(--brand)] bg-[var(--brand-light)] p-3 text-xs text-[var(--brand)]">
                <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>点击「创建并进入编辑器」会跳转到画布视图,可在画布上继续调整节点与连接。</span>
              </div>
            </div>
          )}

          <div className="mt-6 flex items-center justify-between border-t border-[var(--border)] pt-4">
            <button
              type="button"
              onClick={() => setStep((step > 1 ? step - 1 : 1) as 1 | 2 | 3)}
              disabled={step === 1}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] px-3 py-2 text-xs font-semibold text-[var(--text-secondary)] disabled:cursor-not-allowed disabled:opacity-50 hover:border-[var(--brand)] hover:text-[var(--brand)]"
            >
              <ArrowRight className="h-3.5 w-3.5 rotate-180" />上一步
            </button>
            {step < 3 ? (
              <button
                type="button"
                onClick={() => setStep((step + 1) as 2 | 3)}
                disabled={!canNext}
                className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white hover:bg-[var(--brand-hover)] disabled:cursor-not-allowed disabled:opacity-50"
              >
                下一步 <ArrowRight className="h-3.5 w-3.5" />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSubmit}
                disabled={createWorkflow.isPending}
                className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white hover:bg-[var(--brand-hover)] disabled:cursor-not-allowed disabled:opacity-50"
              >
                <FileCheck2 className="h-3.5 w-3.5" />创建并进入编辑器
              </button>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
