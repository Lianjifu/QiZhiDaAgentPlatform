/**
 * 视觉基元 — Sparkline / StepIndicator / EvalProgress / PanelPagination。
 */
import { CheckCircle2, ChevronLeft, ChevronRight, Play } from 'lucide-react';

export function StepIndicator({ current, total, labels }: { current: number; total: number; labels: string[] }) {
  return (
    <div className="flex items-center gap-2">
      {Array.from({ length: total }).map((_, idx) => {
        const stepNum = idx + 1;
        const isActive = stepNum === current;
        const isDone = stepNum < current;
        return (
          <div key={stepNum} className="flex items-center gap-2">
            <div className="flex items-center gap-2">
              <span
                className={`grid h-6 w-6 place-items-center rounded-full text-[10px] font-semibold ${
                  isActive || isDone ? 'bg-[var(--brand)] text-white' : 'bg-[var(--bg-elevated)] text-[var(--text-muted)]'
                }`}
              >
                {isDone ? <CheckCircle2 className="h-3 w-3" /> : stepNum}
              </span>
              <span className={`text-[11px] font-medium ${isActive ? 'text-[var(--brand)]' : 'text-[var(--text-muted)]'}`}>
                {labels[idx]}
              </span>
            </div>
            {stepNum < total && <span className={`h-px w-8 ${isDone ? 'bg-[var(--brand)]' : 'bg-[var(--border)]'}`} />}
          </div>
        );
      })}
    </div>
  );
}

export function EvalProgress({ progress }: { progress: number }) {
  const total = 12;
  const current = Math.min(Math.ceil((progress / 100) * total), total);
  return (
    <div className="rounded-2xl border border-[var(--brand)] bg-[var(--brand-light)]/30 p-4">
      <div className="flex items-center justify-between text-xs">
        <span className="inline-flex items-center gap-2 font-semibold text-[var(--brand)]">
          <Play className="h-3.5 w-3.5" />正在运行评测
        </span>
        <span className="tabular-nums text-[var(--text-muted)]">{progress}%</span>
      </div>
      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-[var(--bg-elevated)]">
        <div className="h-full bg-[var(--brand)] transition-all duration-200" style={{ width: `${progress}%` }} />
      </div>
      <p className="mt-2 text-[11px] text-[var(--text-muted)]">执行用例 {current}/{total}</p>
    </div>
  );
}

export function PanelPagination({ page, totalPages, total, pageStart, pageEnd, onPageChange }: {
  page: number;
  totalPages: number;
  total: number;
  pageStart: number;
  pageEnd: number;
  onPageChange: (next: number) => void;
}) {
  if (totalPages <= 1) return null;
  const safePage = Math.min(page, totalPages);
  return (
    <nav aria-label="分页" className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] px-4 py-2.5 text-xs">
      <span className="text-[var(--text-muted)]">
        第 <span className="font-semibold tabular-nums text-[var(--text)]">{pageStart}-{pageEnd}</span> 个 / 共 <span className="font-semibold tabular-nums text-[var(--text)]">{total}</span> 个
      </span>
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => onPageChange(Math.max(1, safePage - 1))}
          disabled={safePage <= 1}
          aria-label="上一页"
          className="inline-flex items-center gap-1 rounded-lg border border-[var(--border)] px-2.5 py-1 text-[11px] font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)] disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ChevronLeft className="h-3 w-3" />上一页
        </button>
        {Array.from({ length: totalPages }, (_, i) => i + 1).map((n) => {
          const active = n === safePage;
          return (
            <button
              key={n}
              type="button"
              onClick={() => onPageChange(n)}
              aria-current={active ? 'page' : undefined}
              aria-label={`第 ${n} 页`}
              className={`grid h-7 w-7 place-items-center rounded-lg text-[11px] font-semibold transition ${active ? 'bg-[var(--brand)] text-white' : 'border border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]'}`}
            >
              {n}
            </button>
          );
        })}
        <button
          type="button"
          onClick={() => onPageChange(Math.min(totalPages, safePage + 1))}
          disabled={safePage >= totalPages}
          aria-label="下一页"
          className="inline-flex items-center gap-1 rounded-lg border border-[var(--border)] px-2.5 py-1 text-[11px] font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)] disabled:cursor-not-allowed disabled:opacity-40"
        >
          下一页<ChevronRight className="h-3 w-3" />
        </button>
      </div>
    </nav>
  );
}
