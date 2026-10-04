import type { ReactNode } from 'react';

interface BrandLogoProps {
  size?: number;
  withWordmark?: boolean;
  wordmark?: ReactNode;
  subtitle?: ReactNode | false;
  className?: string;
  wordmarkClassName?: string;
  subtitleClassName?: string;
  ariaLabel?: string;
}

/** 搭：对扣积木；智：接缝处的光点。与伙伴平台 wordmark 同源。 */
export function BrandMark({ size = 32 }: { size?: number }) {
  const height = Math.round((size * 56) / 72);
  return (
    <svg
      width={size}
      height={height}
      viewBox="12 32 72 56"
      xmlns="http://www.w3.org/2000/svg"
      focusable="false"
      className="shrink-0"
    >
      <path d="M15 36 H39 V51 A9 9 0 0 1 39 69 V84 H15 Z" fill="#4f46e5" />
      <path d="M81 36 H57 V51 A9 9 0 0 0 57 69 V84 H81 Z" fill="#8b5cf6" />
      <circle cx="48" cy="60" r="4.2" fill="#fff" />
    </svg>
  );
}

export function BrandLogo({
  size = 36,
  withWordmark = false,
  wordmark,
  subtitle,
  className,
  wordmarkClassName,
  subtitleClassName,
  ariaLabel = '企智搭 · 智能体平台',
}: BrandLogoProps) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className ?? ''}`} aria-label={ariaLabel}>
      <span aria-hidden="true">
        <BrandMark size={size} />
      </span>
      {withWordmark && (
        <span className="flex min-w-0 flex-col leading-tight">
          <span className={wordmarkClassName ?? 'text-[15px] font-bold tracking-tight text-[#4f46e5]'}>
            {wordmark ?? '企智搭'}
          </span>
          {subtitle !== false && (
            <span className={subtitleClassName ?? 'mt-0.5 truncate text-[10px] tracking-wide text-[var(--text-muted)]'}>
              {subtitle ?? '智能体平台'}
            </span>
          )}
        </span>
      )}
    </span>
  );
}
