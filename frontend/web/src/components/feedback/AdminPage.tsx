import type { ReactNode } from 'react';

/**
 * 管理台页面外壳 —— 46 个管理侧页面的外框一模一样 ✓
 * （``mx-auto max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-10`` ✓）。
 * 各页自己写一遍只是复制 —— 这里收成一处 ✓。
 *
 * ⚠️ **``pageClass`` 是给页面留的 CSS 钩子** ✓ —— ``.skills-page`` ✓
 * （global.css 里还改过 padding ✓）、``.workflow-page`` ✓（react-flow 控件样式 ✓）
 * —— **别删** ✓。
 */

const DENSITY: Record<'sm' | 'md' | 'lg', string> = {
  sm: 'space-y-4',
  md: 'space-y-5',
  lg: 'space-y-6',
};

export interface AdminPageProps {
  children: ReactNode;
  /** 页面专属 class（CSS 钩子）✓ */
  pageClass?: string;
  /** 纵向间距 —— 默认 ``space-y-6`` ✓ */
  density?: keyof typeof DENSITY;
}

export function AdminPage({ children, pageClass, density = 'lg' }: AdminPageProps) {
  const classes = [
    pageClass,
    'mx-auto w-full max-w-[1440px]',
    DENSITY[density],
    'p-5 pb-16 sm:p-8 xl:px-10',
  ]
    .filter(Boolean)
    .join(' ');
  return <div className={classes}>{children}</div>;
}
