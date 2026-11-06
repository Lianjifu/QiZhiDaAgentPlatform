import type { LucideIcon } from 'lucide-react';
import { CheckCircle2, X } from 'lucide-react';

/**
 * 管理台批量操作条 —— 10 个管理域各抄了一份同样的壳子 ✓
 * （``border-[var(--brand)] bg-[var(--brand-light)]`` + 「已选 N 项」✓
 * + 一排按钮 ✓），只有**按钮集合**和**按钮色调**不同 ✓ → 这里收成配置式 ✓。
 */

export type AdminBatchTone = 'brand' | 'neutral' | 'amber' | 'emerald' | 'rose';

const TONE_CLASS: Record<AdminBatchTone, string> = {
  brand:
    'border-[var(--brand)] bg-[var(--surface-1)] text-[var(--brand)] hover:bg-[var(--brand-light)]',
  neutral:
    'border-[var(--border)] bg-[var(--surface-1)] text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]',
  amber:
    'border-amber-200 bg-[var(--surface-1)] text-amber-700 hover:bg-amber-50 dark:border-amber-500/40 dark:text-amber-300 dark:hover:bg-amber-500/15',
  emerald:
    'border-emerald-200 bg-[var(--surface-1)] text-emerald-700 hover:bg-emerald-50 dark:border-emerald-500/40 dark:text-emerald-300 dark:hover:bg-emerald-500/15',
  rose:
    'border-rose-200 bg-[var(--surface-1)] text-rose-600 hover:bg-rose-50 dark:border-rose-500/40 dark:text-rose-300 dark:hover:bg-rose-500/15',
};

export interface AdminBatchAction {
  id: string;
  label: string;
  onClick: () => void;
  icon?: LucideIcon;
  tone?: AdminBatchTone;
}

export interface AdminBatchBarProps {
  count: number;
  actions: AdminBatchAction[];
  onClear: () => void;
  /** 左侧计数前面的图标 ✓ */
  icon?: LucideIcon;
}

export function AdminBatchBar({ count, actions, onClear, icon }: AdminBatchBarProps) {
  if (count === 0) return null;
  const CountIcon = icon ?? CheckCircle2;
  return (
    <section
      aria-label="批量操作"
      className="flex flex-wrap items-center gap-3 rounded-2xl border border-[var(--brand)] bg-[var(--brand-light)] px-4 py-3 sm:px-5"
    >
      <div className="flex items-center gap-2 text-sm font-semibold text-[var(--brand)]">
        <CountIcon className="h-4 w-4" />
        已选 {count} 项
      </div>
      <div className="ml-auto flex flex-wrap items-center gap-2">
        {actions.map((action) => {
          const Icon = action.icon;
          return (
            <button
              key={action.id}
              type="button"
              onClick={action.onClick}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-semibold ${TONE_CLASS[action.tone ?? 'brand']}`}
            >
              {Icon ? <Icon className="h-3.5 w-3.5" /> : null}
              {action.label}
            </button>
          );
        })}
        <button
          type="button"
          onClick={onClear}
          className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-semibold text-[var(--text-muted)] hover:text-[var(--brand)]"
        >
          <X className="h-3.5 w-3.5" />
          取消选择
        </button>
      </div>
    </section>
  );
}
