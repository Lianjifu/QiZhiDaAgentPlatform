import type { ReactNode } from 'react';

/**
 * 管理台页头（hero）—— 15 个管理域的页头**结构完全一样** ✓：
 * 一个渐变装饰块 + 眉标 + 大标题 + 一行说明 ✓。
 * 各域只差**配色** ✓（gradient + eyebrow 颜色 ✓）—— 这里收成一张色调表 ✓。
 */

export type AdminHeroTone =
  | 'brand'
  | 'teal'
  | 'amber'
  | 'indigo'
  | 'violet'
  | 'purple'
  | 'sky'
  | 'blue'
  | 'emerald'
  | 'rose';

const TONES: Record<AdminHeroTone, { gradient: string; eyebrow: string }> = {
  brand: { gradient: 'var(--brand-light)', eyebrow: 'text-[var(--brand)]' },
  teal: { gradient: 'rgba(20,184,166,0.10)', eyebrow: 'text-teal-700 dark:text-teal-300' },
  amber: { gradient: 'rgba(245,158,11,0.10)', eyebrow: 'text-amber-700 dark:text-amber-300' },
  indigo: { gradient: 'rgba(99,102,241,0.10)', eyebrow: 'text-indigo-700 dark:text-indigo-300' },
  violet: { gradient: 'rgba(168,85,247,0.10)', eyebrow: 'text-violet-700 dark:text-violet-300' },
  purple: { gradient: 'rgba(139,92,246,0.10)', eyebrow: 'text-violet-700 dark:text-violet-300' },
  sky: { gradient: 'rgba(14,165,233,0.10)', eyebrow: 'text-sky-700 dark:text-sky-300' },
  blue: { gradient: 'rgba(59,130,246,0.08)', eyebrow: 'text-[var(--brand)]' },
  emerald: { gradient: 'rgba(34,197,94,0.10)', eyebrow: 'text-emerald-700 dark:text-emerald-300' },
  rose: { gradient: 'rgba(244,63,94,0.10)', eyebrow: 'text-rose-700 dark:text-rose-300' },
};

export interface AdminHeroProps {
  /** 眉标 —— 形如 ``ADMIN / 智能体管理`` ✓ */
  eyebrow: string;
  /** 大标题 ✓ */
  title: string;
  /** 标题下面那行说明（通常是统计）✓ */
  description?: ReactNode;
  /** 配色 ✓ */
  tone?: AdminHeroTone;
  /** 右侧插槽（概览页的时间范围下拉 ✓）✓ */
  aside?: ReactNode;
  /** 标题层级 —— 列表页用 h2 ✓，主列表页用 h1 ✓ */
  headingLevel?: 'h1' | 'h2';
}

export function AdminHero({
  eyebrow,
  title,
  description,
  tone = 'brand',
  aside,
  headingLevel = 'h2',
}: AdminHeroProps) {
  const palette = TONES[tone];
  const Heading = headingLevel;
  return (
    <section className="relative overflow-hidden rounded-[28px] border border-[var(--border)] bg-[var(--surface-1)] px-6 py-8 shadow-[var(--shadow-sm)] sm:px-8">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden rounded-[28px]">
        <div
          className="absolute right-0 top-0 h-full w-1/2"
          style={{ background: `radial-gradient(circle_at_top_right,${palette.gradient},transparent_68%)` }}
        />
      </div>
      <div
        className={
          aside
            ? 'relative flex flex-col justify-between gap-6 xl:flex-row xl:items-end'
            : 'relative'
        }
      >
        <div>
          <p className={`text-[11px] font-semibold uppercase tracking-[0.22em] ${palette.eyebrow}`}>
            {eyebrow}
          </p>
          <Heading className="mt-3 text-2xl font-semibold tracking-tight sm:text-3xl xl:text-4xl">
            {title}
          </Heading>
          {description ? (
            <p className="mt-3 max-w-2xl text-sm leading-7 text-[var(--text-muted)]">{description}</p>
          ) : null}
        </div>
        {aside}
      </div>
    </section>
  );
}
