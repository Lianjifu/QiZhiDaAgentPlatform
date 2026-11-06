/**
 * **资源列表** ✓ —— 工具栏 + 卡片网格 + 空态 ✓（四类资源共用 ✓）。
 *
 * ⚠️ **这里只画** ✓ —— 数据 ✓ / 筛选 ✓ / 动作 ✓ 全部由 kind 组件传进来 ✓
 * （它知道原始类型 ✓）。
 */

import { Heart } from 'lucide-react';
import type { ReactNode } from 'react';

import { CardActionButton, CardActions, CatalogToolbar, EmptyFilterState } from '../components';
import type { CatalogFilter } from '../components';
import type { ResourceItem } from './schema';

export function ResourceSection({
  items,
  query,
  onQuery,
  searchLabel,
  placeholder,
  filters = [],
  countLabel,
  favorited,
  onToggleFavorite,
  onOpenDetails,
  chosen,
  onToggleChosen,
  detailsLabel,
  empty,
  loading = false,
}: {
  items: ResourceItem[];
  query: string;
  onQuery: (value: string) => void;
  searchLabel: string;
  placeholder: string;
  filters?: CatalogFilter[];
  countLabel?: string;
  favorited: string[];
  onToggleFavorite: (id: string) => void;
  onOpenDetails: (item: ResourceItem, trigger: HTMLElement) => void;
  chosen: string[];
  onToggleChosen: (id: string) => void;
  detailsLabel: string;
  empty: { title: string; description: string; action?: ReactNode };
  loading?: boolean;
}) {
  return (
    <section
      aria-label={searchLabel}
      className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]"
    >
      <CatalogToolbar
        search={query}
        onSearch={onQuery}
        searchLabel={searchLabel}
        placeholder={placeholder}
        filters={filters}
        countLabel={countLabel}
      />
      {items.length ? (
        <div className="grid gap-4 p-5 md:grid-cols-2 xl:grid-cols-3">
          {items.map((item) => {
            const Icon = item.icon;
            const favorite = favorited.includes(item.id);
            const isChosen = chosen.includes(item.id);
            return (
              <article
                key={item.id}
                className="group flex min-h-[248px] min-w-0 flex-col rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 transition hover:border-[var(--brand)] hover:shadow-[var(--shadow-sm)]"
              >
                <div className="flex items-start justify-between gap-3">
                  <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${item.tone}`}>
                    <Icon className="h-5 w-5" />
                  </span>
                  <div className="flex items-center gap-1">
                    {item.badge ? (
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                          item.badge.tone === 'ok'
                            ? 'bg-[var(--success-bg)] text-[var(--success)]'
                            : 'bg-[var(--bg-hover)] text-[var(--text-muted)]'
                        }`}
                      >
                        {item.badge.label}
                      </span>
                    ) : null}
                    <button
                      type="button"
                      aria-label={`${favorite ? '取消收藏' : '收藏'}${item.name}`}
                      aria-pressed={favorite}
                      onClick={() => onToggleFavorite(item.id)}
                      className={`rounded-lg p-2 transition ${
                        favorite
                          ? 'text-rose-600'
                          : 'text-[var(--text-muted)] hover:text-rose-600'
                      }`}
                    >
                      <Heart className="h-4 w-4" fill={favorite ? 'currentColor' : 'none'} />
                    </button>
                  </div>
                </div>
                <p className="mt-4 text-[11px] font-medium text-[var(--text-muted)]">{item.meta}</p>
                <button
                  type="button"
                  onClick={(event) => onOpenDetails(item, event.currentTarget)}
                  className="mt-1 text-left text-base font-semibold hover:text-[var(--brand)]"
                >
                  {item.name}
                </button>
                <p className="mt-2 line-clamp-2 text-xs leading-6 text-[var(--text-muted)]">
                  {item.description}
                </p>
                <CardActions>
                  <CardActionButton
                    aria-label={`移出${item.name}`}
                    onClick={() => onToggleChosen(item.id)}
                  >
                    {isChosen ? '移出' : '选用'}
                  </CardActionButton>
                  <CardActionButton onClick={(event) => onOpenDetails(item, event.currentTarget)}>
                    {detailsLabel}
                  </CardActionButton>
                  <CardActionButton
                    tone="brand"
                    disabled={item.primary.disabled}
                    onClick={item.primary.run}
                  >
                    {item.primary.icon ? <item.primary.icon className="h-3.5 w-3.5" /> : null}
                    {item.primary.label}
                  </CardActionButton>
                </CardActions>
              </article>
            );
          })}
        </div>
      ) : (
        <EmptyFilterState title={empty.title} description={empty.description} action={empty.action} />
      )}
      {loading && !items.length ? (
        <p className="px-5 pb-5 text-xs text-[var(--text-muted)]">加载中…</p>
      ) : null}
    </section>
  );
}
