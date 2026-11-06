import type { LucideIcon } from 'lucide-react';
import { Search } from 'lucide-react';

/**
 * 管理台「没有匹配的 X」空态 —— 8 个列表页抄了同一段 ✓。
 * ``variant``:
 * - ``inline`` —— 列表内嵌 ✓（列表容器下面 ✓）
 * - ``dashed`` —— 独立虚线框 ✓（整页没有内容时 ✓）
 */

export interface AdminEmptyStateProps {
  title: string;
  description?: string;
  icon?: LucideIcon;
  variant?: 'inline' | 'dashed';
}

export function AdminEmptyState({
  title,
  description = '尝试其他关键词或清除筛选。',
  icon,
  variant = 'inline',
}: AdminEmptyStateProps) {
  const Icon = icon ?? Search;
  const shell =
    variant === 'dashed'
      ? 'mt-5 rounded-2xl border border-dashed border-[var(--border-strong)] p-12 text-center'
      : 'px-5 pb-8 text-center';
  return (
    <div className={shell}>
      <Icon className="mx-auto h-6 w-6 text-[var(--text-muted)]" />
      <p className="mt-3 text-sm font-semibold">{title}</p>
      <p className="mt-1 text-xs text-[var(--text-muted)]">{description}</p>
    </div>
  );
}
