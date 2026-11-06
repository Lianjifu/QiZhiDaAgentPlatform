/**
 * 管理侧「新建知识库」独立页面 — 路由 /admin/knowledge/kbs/new
 *
 * 顶部返回知识管理;左 1/3 sticky 纵向 stepper + Info 提示;
 * 右 2/3 workspace 卡片(创建按钮集中在右侧 CreateKbPreview 底部)。
 * step state 受控在本页;wizard 接 controlledStep + onStepChange + draft。
 */
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, ArrowRight, BookOpen, CheckCircle2, Database, Info, Search } from 'lucide-react';
import type { CreateKbVars } from './schema';
import { useKnowledgeSources, useCreateKb } from './useKnowledge';
import CreateKbWizard from './components/CreateKbWizard';
import { AdminPage } from '@/components/feedback/AdminPage';

type Step = 1 | 2 | 3;

const STEPS: { key: string; index: Step; title: string; description: string; icon: typeof BookOpen }[] = [
  { key: 'basic', index: 1, title: '基础信息', description: '命名、说明与可见范围', icon: BookOpen },
  { key: 'sources', index: 2, title: '数据源', description: '选择要纳入的数据源', icon: Database },
  { key: 'retrieval', index: 3, title: '检索设置', description: '检索方式与 Top K', icon: Search },
];

export default function KbCreatePage() {
  const navigate = useNavigate();
  const sourcesQuery = useKnowledgeSources();
  const createKb = useCreateKb();
  const sources = sourcesQuery.data ?? [];
  const [step, setStep] = useState<Step>(1);

  const handleSubmit = (vars: CreateKbVars) => {
    createKb.mutate(vars, {
      onSuccess: (created) => navigate(`/admin/knowledge/kbs/${created.id}`),
      onError: () => navigate('/admin/knowledge'),
    });
  };

  const activeStep = STEPS.find((s) => s.index === step) ?? STEPS[0];

  return (
    <AdminPage density="lg">
      <Link
        to="/admin/knowledge"
        className="inline-flex w-fit items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--brand)]"
      >
        <ArrowLeft className="h-3.5 w-3.5" />返回知识管理
      </Link>

      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--brand)]">
            知识管理
          </p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">新建知识库</h1>
        </div>
        <p className="max-w-sm text-xs leading-5 text-[var(--text-muted)]">
          填写后将自动同步数据源,完成后可关联到 Agent。
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        <aside aria-label="创建步骤" className="lg:sticky lg:top-5 lg:self-start">
          <ol className="relative space-y-1">
            {STEPS.map((s) => {
              const active = step === s.index;
              const done = step > s.index;
              const Icon = s.icon;
              return (
                <li key={s.key}>
                  <button
                    type="button"
                    onClick={() => setStep(s.index)}
                    aria-current={active ? 'step' : undefined}
                    className={`flex w-full items-start gap-3 rounded-xl px-3 py-3 text-left transition ${
                      active ? 'bg-[var(--brand-light)]' : 'hover:bg-[var(--bg-hover)]'
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
                      {done ? <CheckCircle2 className="h-4 w-4" /> : <Icon className="h-4 w-4" />}
                    </span>
                    <span className="min-w-0 flex-1 pt-0.5">
                      <span
                        className={`text-[11px] font-semibold uppercase tracking-wide ${
                          active ? 'text-[var(--brand)]' : 'text-[var(--text-muted)]'
                        }`}
                      >
                        第 {s.index} 步
                      </span>
                      <span
                        className={`mt-0.5 block text-sm font-semibold ${
                          active ? 'text-[var(--text)]' : 'text-[var(--text-secondary)]'
                        }`}
                      >
                        {s.title}
                      </span>
                      <span className="mt-0.5 block text-[11px] leading-4 text-[var(--text-muted)]">
                        {s.description}
                      </span>
                    </span>
                    {active && (
                      <ArrowRight className="mt-3 h-3.5 w-3.5 shrink-0 text-[var(--brand)]" />
                    )}
                  </button>
                </li>
              );
            })}
          </ol>

          <div className="mt-2 flex items-start gap-2 rounded-xl border border-dashed border-[var(--border)] p-3 text-[11px] leading-4 text-[var(--text-muted)]">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--brand)]" />
            <span>
              完成后 docCount 与 Top K 决定召回质量;创建后可随时调整数据源与检索参数。
            </span>
          </div>
        </aside>

        <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6">
          <div className="mb-5 flex items-center justify-between border-b border-[var(--border)] pb-4">
            <div className="flex items-center gap-2">
              <BookOpen className="h-4 w-4 text-[var(--brand)]" />
              <h2 className="text-sm font-semibold">{activeStep.title}</h2>
            </div>
            <span className="text-[11px] font-medium tabular-nums text-[var(--text-muted)]">
              {step} / {STEPS.length}
            </span>
          </div>
          <CreateKbWizard
            sources={sources}
            controlledStep={step}
            onStepChange={setStep}
            onSubmit={handleSubmit}
            isSubmitting={createKb.isPending}
          />
        </section>
      </div>
    </AdminPage>
  );
}