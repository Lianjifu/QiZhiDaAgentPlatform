import type { ReactNode } from 'react';

/** 品牌主色，对齐企智搭标识规范。 */
export const BRAND_PURPLE = '#6828D8';
export const BRAND_ORANGE = '#F87818';
export const BRAND_MONO = '#1A1A1A';
const BRAND_MONO_FRONT = '#3A3A3A';
const ICON_BACK = '#E4D4FF';

interface BrandLogoProps {
  size?: number;
  /** mark: 透明底叠合方块；icon: 紫底圆角图标；mono: 单色。 */
  variant?: 'mark' | 'icon' | 'mono';
  layout?: 'horizontal' | 'stacked';
  /** stacked 时图形与文字对齐；登录页左栏用 start。 */
  align?: 'start' | 'center';
  withWordmark?: boolean;
  wordmark?: ReactNode;
  subtitle?: ReactNode | false;
  caption?: ReactNode | false;
  className?: string;
  wordmarkClassName?: string;
  subtitleClassName?: string;
  captionClassName?: string;
  ariaLabel?: string;
}

function OverlapBlocks({ back, front, gap }: { back: string; front: string; gap: string }) {
  return (
    <>
      <rect x="6" y="26" width="44" height="44" rx="13" fill={back} />
      <rect x="26.5" y="2.5" width="51" height="51" rx="15.5" fill={gap} />
      <rect x="30" y="6" width="44" height="44" rx="13" fill={front} />
    </>
  );
}

/** 两块圆角方块层叠咬合，白色间隙象征「搭」。 */
export function BrandMark({
  size = 32,
  variant = 'mark',
}: {
  size?: number;
  variant?: 'mark' | 'icon' | 'mono';
}) {
  if (variant === 'icon') {
    return (
      <svg width={size} height={size} viewBox="0 0 80 80" xmlns="http://www.w3.org/2000/svg" focusable="false" className="shrink-0">
        <rect width="80" height="80" rx="18" fill={BRAND_PURPLE} />
        <g transform="translate(10 10) scale(0.75)">
          <OverlapBlocks back={ICON_BACK} front={BRAND_ORANGE} gap="#fff" />
        </g>
      </svg>
    );
  }

  const back = variant === 'mono' ? BRAND_MONO : BRAND_PURPLE;
  const front = variant === 'mono' ? BRAND_MONO_FRONT : BRAND_ORANGE;
  return (
    <svg width={size} height={size} viewBox="4 2 74 72" xmlns="http://www.w3.org/2000/svg" focusable="false" className="shrink-0">
      <OverlapBlocks back={back} front={front} gap="#fff" />
    </svg>
  );
}

export function BrandLogo({
  size = 36,
  variant = 'mark',
  layout = 'horizontal',
  align = 'center',
  withWordmark = false,
  wordmark,
  subtitle,
  caption,
  className,
  wordmarkClassName,
  subtitleClassName,
  captionClassName,
  ariaLabel = '企智搭 · 智能体平台',
}: BrandLogoProps) {
  const stacked = layout === 'stacked';
  const resolvedSubtitle = subtitle === false ? false : (subtitle ?? '智能体平台');
  const resolvedCaption =
    caption === false ? false : caption !== undefined ? caption : stacked ? 'QIZHIDA' : false;
  const stackAlign = align === 'start' ? 'items-start' : 'items-center';

  return (
    <span
      className={`inline-flex ${stacked ? `flex-col ${stackAlign} gap-3` : 'items-center gap-2.5'} ${className ?? ''}`}
      aria-label={ariaLabel}
    >
      <span aria-hidden="true">
        <BrandMark size={size} variant={variant} />
      </span>
      {withWordmark && (
        <span className={`flex min-w-0 flex-col leading-tight ${stacked ? stackAlign : ''}`}>
          <span
            className={
              wordmarkClassName ??
              `font-bold tracking-tight ${stacked ? 'text-[28px]' : 'text-[15px]'} ${
                variant === 'mono' ? 'text-[#1A1A1A]' : 'text-[#6828D8]'
              }`
            }
          >
            {wordmark ?? '企智搭'}
          </span>
          {resolvedSubtitle !== false && (
            <span
              className={
                subtitleClassName ??
                (stacked
                  ? 'mt-1.5 text-[13px] leading-none text-[var(--login-fg-muted,var(--text-muted))]'
                  : 'mt-0.5 truncate text-[10px] leading-none tracking-wide text-[var(--text-muted)]')
              }
            >
              {resolvedSubtitle}
            </span>
          )}
          {resolvedCaption !== false && (
            <span
              className={
                captionClassName ??
                'mt-2 text-[11px] font-semibold tracking-[0.42em] text-[#F87818]'
              }
            >
              {resolvedCaption}
            </span>
          )}
        </span>
      )}
    </span>
  );
}
