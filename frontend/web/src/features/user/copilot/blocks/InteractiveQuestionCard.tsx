/**
 * InteractiveQuestionCard — 多选问题 modal.
 *
 * 弹窗模式: 居中卡片, 每个 question 一个 section, 单选/复选由
 * multi_select 决定. 提交按钮 disabled 除非所有 question 都选了.
 * ESC 或点 X = 跳过 (后端收到空 answers, 默认占位).
 */
import { useEffect, useState } from 'react';
import { Check, Circle, X } from 'lucide-react';
import type {
  AnswerPayload,
  PendingQuestion,
  QuestionSpec,
} from '../interactiveStore';

function QuestionSection({
  question,
  index,
  onChange,
}: {
  question: QuestionSpec;
  index: number;
  onChange: (selected: string[]) => void;
}) {
  const [selected, setSelected] = useState<string[]>([]);
  const multi = question.multi_select === true;

  const toggle = (label: string) => {
    if (multi) {
      setSelected((current) =>
        current.includes(label)
          ? current.filter((c) => c !== label)
          : [...current, label],
      );
    } else {
      setSelected([label]);
    }
  };

  useEffect(() => {
    onChange(selected);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  return (
    <section className="rounded-xl border border-[var(--border)] bg-[var(--surface-1)] p-4">
      <header className="mb-3 flex items-start justify-between gap-3">
        <div>
          {question.header && (
            <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--brand)]">
              {question.header}
            </p>
          )}
          <h3 className="mt-1 text-sm font-semibold text-[var(--text)]">
            {question.question}
          </h3>
        </div>
        <span className="shrink-0 rounded-md bg-[var(--bg-elevated)] px-2 py-0.5 text-[10px] text-[var(--text-muted)]">
          问题 {index + 1} / {multi ? '多选' : '单选'}
        </span>
      </header>
      <ul className="space-y-2">
        {question.options.map((opt) => {
          const checked = selected.includes(opt.label);
          return (
            <li key={opt.label}>
              <button
                type="button"
                onClick={() => toggle(opt.label)}
                aria-pressed={checked}
                className={`flex w-full items-start gap-3 rounded-lg border px-3 py-2 text-left transition ${
                  checked
                    ? 'border-[var(--brand)] bg-[var(--brand-light)] text-[var(--brand)]'
                    : 'border-[var(--border)] bg-[var(--surface-1)] hover:border-[var(--brand)] hover:bg-[var(--bg-hover)]'
                }`}
              >
                {multi ? (
                  checked ? (
                    <Check className="mt-0.5 h-4 w-4 shrink-0" />
                  ) : (
                    <Circle className="mt-0.5 h-4 w-4 shrink-0 text-[var(--text-muted)]" />
                  )
                ) : (
                  <span
                    className={`mt-1 inline-block h-3 w-3 shrink-0 rounded-full border-2 ${
                      checked
                        ? 'border-[var(--brand)] bg-[var(--brand)]'
                        : 'border-[var(--text-muted)] bg-transparent'
                    }`}
                    aria-hidden
                  />
                )}
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium">{opt.label}</span>
                  {opt.description && (
                    <span className="mt-0.5 block text-[11px] leading-5 text-[var(--text-muted)]">
                      {opt.description}
                    </span>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function InteractiveQuestionCard({
  pending,
  onDismiss,
}: {
  pending: PendingQuestion;
  onDismiss: () => void;
}) {
  const [answers, setAnswers] = useState<Record<number, string[]>>({});
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onDismiss();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onDismiss]);

  const allAnswered = pending.questions.every(
    (_, i) => (answers[i] || []).length > 0,
  );

  const submit = async () => {
    if (!allAnswered) return;
    setSubmitting(true);
    try {
      const payload: AnswerPayload[] = pending.questions.map((_, i) => ({
        question_index: i,
        selected: answers[i] || [],
      }));
      await pending.onResolve(payload);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="interactive-question-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4"
    >
      <div className="relative flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] shadow-[var(--shadow-md)]">
        <header className="flex items-center justify-between border-b border-[var(--border)] px-5 py-4">
          <h2
            id="interactive-question-title"
            className="text-sm font-semibold text-[var(--text)]"
          >
            需要你的选择
          </h2>
          <button
            type="button"
            onClick={onDismiss}
            className="rounded-md p-1.5 text-[var(--text-muted)] hover:bg-[var(--bg-hover)]"
            aria-label="关闭"
          >
            <X className="h-4 w-4" />
          </button>
        </header>
        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          {pending.questions.map((q, i) => (
            <QuestionSection
              key={i}
              index={i}
              question={q}
              onChange={(selected) =>
                setAnswers((current) => ({ ...current, [i]: selected }))
              }
            />
          ))}
        </div>
        <footer className="flex items-center justify-end gap-2 border-t border-[var(--border)] bg-[var(--bg-elevated)] px-5 py-3">
          <button
            type="button"
            onClick={onDismiss}
            className="rounded-md px-3 py-2 text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"
          >
            跳过
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!allAnswered || submitting}
            className="rounded-md bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {submitting ? '提交中…' : '提交答案'}
          </button>
        </footer>
      </div>
    </div>
  );
}