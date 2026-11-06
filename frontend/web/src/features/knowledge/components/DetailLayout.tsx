/**
 * Admin 知识详情 — 共享 layout 组件。
 * KbDetailPage / DocDetailPage / SourceDetailPage 共用同一形态:
 * wrapper(+ 可选返回 Link)→ DetailHeader → DetailStatGrid → DetailSection → NotFound / Skeleton。
 */
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { AdminPage } from '@/components/feedback/AdminPage';

const BACK_DEFAULT = '/admin/knowledge';

export function DetailShell({
  backTo = BACK_DEFAULT,
  backLabel = '返回知识管理',
  showBack = true,
  children,
}: {
  backTo?: string;
  backLabel?: string;
  showBack?: boolean;
  children: ReactNode;
}) {
  return (
    <AdminPage density="lg">
      {showBack && (
        <Link to={backTo} className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--brand)]">
          <ArrowLeft className="h-3.5 w-3.5" />{backLabel}
        </Link>
      )}
      {children}
    </AdminPage>
  );
}

export type DetailBadge = {
  label: string;
  className: string;
  dot?: string;
};

export function DetailHeader({
  eyebrow,
  title,
  icon: Icon,
  iconClass,
  subtitle,
  badges = [],
  actions,
}: {
  eyebrow?: string;
  title: string;
  icon?: React.ComponentType<{ className?: string }>;
  iconClass?: string;
  subtitle?: string;
  badges?: DetailBadge[];
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0 flex-1">
        {eyebrow && (
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--brand)]">{eyebrow}</p>
        )}
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-xs text-[var(--text-muted)]">{subtitle}</p>}
        {badges.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {badges.map((b, idx) => (
              <span key={idx} className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${b.className}`}>
                {b.dot && <span className={`h-1.5 w-1.5 rounded-full ${b.dot}`} aria-hidden="true" />}
                {b.label}
              </span>
            ))}
          </div>
        )}
      </div>
      {(actions || Icon) && (
        <div className="flex shrink-0 items-center gap-2">
          {actions}
          {!actions && Icon ? (
            <span className={`grid h-12 w-12 place-items-center rounded-xl ${iconClass ?? 'bg-[var(--brand-soft)] text-[var(--brand)]'}`}>
              <Icon className="h-6 w-6" />
            </span>
          ) : null}
        </div>
      )}
    </header>
  );
}

const TONE_TEXT: Record<string, string> = {
  success: 'text-emerald-600 dark:text-emerald-300',
  warn: 'text-amber-600 dark:text-amber-300',
  danger: 'text-rose-600 dark:text-rose-300',
  info: 'text-sky-600 dark:text-sky-300',
  brand: 'text-[var(--brand)]',
};

const STAT_GRID_COLS: Record<2 | 3 | 4 | 5, string> = {
  2: 'grid-cols-1 sm:grid-cols-2',
  3: 'grid-cols-1 sm:grid-cols-3',
  4: 'grid-cols-1 sm:grid-cols-2 xl:grid-cols-4',
  5: 'grid-cols-1 sm:grid-cols-2 xl:grid-cols-5',
};

export function DetailStatGrid({ columns = 4, children }: { columns?: 2 | 3 | 4 | 5; children: ReactNode }) {
  return <section className={`grid gap-3 ${STAT_GRID_COLS[columns]}`}>{children}</section>;
}

export function DetailStat({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: 'success' | 'warn' | 'danger' | 'info' | 'brand';
}) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-1)] p-4">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">{label}</p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${tone ? TONE_TEXT[tone] : 'text-[var(--text)]'}`}>{value}</p>
      {hint && <p className="mt-1 text-[11px] text-[var(--text-muted)]">{hint}</p>}
    </div>
  );
}

export function DetailSection({
  title,
  icon: Icon,
  action,
  children,
}: {
  title?: string;
  icon?: React.ComponentType<{ className?: string }>;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
      {(title || action) && (
        <div className="mb-4 flex items-center justify-between gap-2">
          {title && (
            <div className="flex items-center gap-2 text-xs font-semibold text-[var(--text)]">
              {Icon && <Icon className="h-3.5 w-3.5 text-[var(--brand)]" />}
              {title}
            </div>
          )}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function DetailField({
  icon: Icon,
  label,
  children,
}: {
  icon?: React.ComponentType<{ className?: string }>;
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface-1)] p-3">
      {Icon && (
        <span className="mt-0.5 grid h-7 w-7 place-items-center rounded-md bg-[var(--bg-elevated)] text-[var(--brand)]">
          <Icon className="h-3.5 w-3.5" />
        </span>
      )}
      <div className="min-w-0 flex-1">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">{label}</p>
        <div className="mt-0.5 text-sm text-[var(--text)]">{children}</div>
      </div>
    </div>
  );
}

export function DetailNotFound({ subject = '资源不存在或已被删除' }: { subject?: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-[var(--border)] bg-[var(--surface-1)] p-8 text-center">
      <p className="text-sm font-semibold">{subject}</p>
      <p className="mt-1 text-xs text-[var(--text-muted)]">请返回列表重新选择。</p>
    </div>
  );
}

export function DetailSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      <div className="h-7 w-48 animate-pulse rounded bg-[var(--bg-elevated)]" />
      {Array.from({ length: rows }).map((_, idx) => (
        <div key={idx} className="h-20 animate-pulse rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]" />
      ))}
    </div>
  );
}
