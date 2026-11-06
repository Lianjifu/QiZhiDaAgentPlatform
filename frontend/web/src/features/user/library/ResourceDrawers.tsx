/**
 * **资源抽屉** ✓ —— 详情抽屉 ✓ + 浏览/选用抽屉 ✓（四类资源共用 ✓）。
 */

import { Check, Heart, Search } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { SideDrawer } from '@/components/feedback/SideDrawer';

import type { ResourceCopy, ResourceItem } from './schema';

export function ResourceDetailDrawer({
  item,
  onClose,
  copy,
  favorited,
  onToggleFavorite,
  chosen,
  onToggleChosen,
  onPrimary,
  restoreFocusTo,
}: {
  item: ResourceItem | null;
  onClose: () => void;
  copy: ResourceCopy;
  favorited: boolean;
  onToggleFavorite: () => void;
  chosen: boolean;
  onToggleChosen: () => void;
  onPrimary: () => void;
  /** **打开抽屉的按钮** ✓ —— 关掉后焦点回到那里 ✓ */
  restoreFocusTo?: HTMLElement | null;
}) {
  // ⚠️ **焦点归还** ✓ —— 抽屉关掉后焦点回到打开它的那个按钮 ✓
  // （不然键盘用户被丢回 body ✗✗）。
  useEffect(() => {
    if (item) return;
    restoreFocusTo?.focus?.();
  }, [item, restoreFocusTo]);

  if (!item) return null;
  const Icon = item.icon;
  return (
    <SideDrawer
      open
      onClose={onClose}
      ariaLabel={`${item.name}${copy.detailSuffix ?? '详情'}`}
      eyebrow={<p className="text-[11px] font-semibold text-[var(--brand)]">{copy.eyebrow}</p>}
      closeLabel={`关闭${copy.eyebrow}`}
    >
      <div className={`mt-10 grid h-14 w-14 place-items-center rounded-2xl ${item.tone}`}>
        <Icon className="h-7 w-7" />
      </div>
      <h2 className="mt-5 text-2xl font-semibold">{item.name}</h2>
      <p className="mt-2 text-xs text-[var(--text-muted)]">{item.meta}</p>
      <p className="mt-6 text-sm leading-7 text-[var(--text-secondary)]">{item.description}</p>
      {item.fields.length ? (
        <div className="mt-6 grid gap-3 sm:grid-cols-2">
          {item.fields.map((field) => (
            <div key={field.label} className="rounded-xl bg-[var(--bg-elevated)] p-4">
              <p className="text-xs text-[var(--text-muted)]">{field.label}</p>
              <p className="mt-2 text-sm font-semibold leading-6">{field.value}</p>
            </div>
          ))}
        </div>
      ) : null}
      {item.note ? (
        <div className="mt-5 rounded-xl border border-[var(--border)] p-4">
          <p className="text-xs font-semibold">开始前准备</p>
          <p className="mt-2 text-xs leading-6 text-[var(--text-muted)]">{item.note}</p>
        </div>
      ) : null}
      {item.extra ? <div className="mt-5">{item.extra}</div> : null}
      <div className="mt-7 flex flex-col gap-2 sm:flex-row">
        <button
          type="button"
          onClick={onToggleFavorite}
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-[var(--border)] px-4 py-2.5 text-sm font-semibold"
        >
          <Heart className="h-4 w-4" fill={favorited ? 'currentColor' : 'none'} />
          {favorited ? '取消收藏' : '收藏'}
        </button>
        <button
          type="button"
          onClick={onToggleChosen}
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-[var(--border)] px-4 py-2.5 text-sm font-semibold"
        >
          {chosen ? '取消选用' : '选用'}
        </button>
        <button
          type="button"
          aria-label={item.primary.ariaLabel}
          onClick={onPrimary}
          disabled={item.primary.disabled}
          className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl bg-[var(--brand)] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[var(--brand-hover)] disabled:cursor-not-allowed disabled:opacity-40"
        >
          {item.primary.icon ? <item.primary.icon className="h-4 w-4" /> : null}
          {item.primary.label}
        </button>
      </div>
      {item.extraActions?.length ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {item.extraActions.map((action) => (
            <button
              key={action.label}
              type="button"
              onClick={action.onClick}
              className="inline-flex items-center gap-1.5 rounded-xl border border-[var(--border)] px-3 py-2 text-xs font-semibold hover:border-[var(--brand)] hover:text-[var(--brand)]"
            >
              {action.label}
            </button>
          ))}
        </div>
      ) : null}
    </SideDrawer>
  );
}

export function ResourceBrowserDrawer({
  open,
  onClose,
  items,
  chosen,
  onToggleChosen,
  onPrimary,
  loading,
  copy,
  searchPlaceholder,
  filters = [],
}: {
  open: boolean;
  onClose: () => void;
  items: ResourceItem[];
  chosen: string[];
  onToggleChosen: (id: string) => void;
  onPrimary: (item: ResourceItem) => void;
  loading: boolean;
  copy: ResourceCopy;
  searchPlaceholder: string;
  filters?: { label: string; options: { value: string; label: string }[] }[];
}) {
  const [query, setQuery] = useState('');
  const [filterValues, setFilterValues] = useState<Record<string, string>>({});

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return items.filter((item) => {
      if (needle && !`${item.name} ${item.description} ${item.meta}`.toLowerCase().includes(needle)) {
        return false;
      }
      // ⚠️ **筛选值挂在条目上** ✓（``item.filters`` ✓）—— 抽屉自己管自己的
      // 筛选状态 ✓（与外层工具栏那套互不干扰 ✓）。
      return Object.entries(filterValues).every(([label, value]) => {
        if (value === 'all' || value === '') return true;
        return item.filters?.[label] === value;
      });
    });
  }, [items, query, filterValues]);

  const chosenCount = chosen.length;

  return (
    <SideDrawer
      open={open}
      onClose={onClose}
      ariaLabel={copy.browseTitle}
      eyebrow={<p className="text-[11px] font-semibold text-[var(--brand)]">从开放目录选用</p>}
      closeLabel={`关闭${copy.browseTitle}`}
      panelClassName="flex max-w-xl flex-col"
    >
      <div className="mt-6">
        <h2 className="text-xl font-semibold">{copy.browseTitle}</h2>
        <p className="mt-2 text-xs leading-6 text-[var(--text-muted)]">{copy.browseDescription}</p>
      </div>

      <div className="mt-5 flex flex-col gap-2 sm:flex-row">
        <label className="relative min-w-0 flex-1">
          <span className="sr-only">搜索可选用资源</span>
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-muted)]" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={searchPlaceholder}
            className="h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] pl-9 pr-3 text-sm outline-none focus:border-[var(--brand)]"
          />
        </label>
        {filters.map((filter) => (
          <label key={filter.label} className="shrink-0">
            <span className="sr-only">{filter.label}</span>
            <select
              aria-label={filter.label}
              value={filterValues[filter.label] ?? 'all'}
              onChange={(event) =>
                setFilterValues((current) => ({ ...current, [filter.label]: event.target.value }))
              }
              className="h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)] sm:w-36"
            >
              {filter.options.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>

      <p className="mt-3 text-[11px] tabular-nums text-[var(--text-muted)]">
        {loading ? '同步中…' : `${visible.length} 项可浏览 · 已选用 ${chosenCount}`}
      </p>

      <ul className="mt-4 flex-1 space-y-3 overflow-y-auto pb-24">
        {visible.length === 0 ? (
          <li className="rounded-xl border border-dashed border-[var(--border)] px-4 py-10 text-center text-xs text-[var(--text-muted)]">
            {copy.emptyTitle}
          </li>
        ) : (
          visible.map((item) => {
            const isChosen = chosen.includes(item.id);
            const Icon = item.icon;
            return (
              <li key={item.id} className="rounded-xl border border-[var(--border)] p-4">
                <div className="flex items-start gap-3">
                  <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${item.tone}`}>
                    <Icon className="h-4 w-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-[11px] text-[var(--text-muted)]">{item.meta}</p>
                    <p className="mt-1 text-sm font-semibold">{item.name}</p>
                    <p className="mt-1 line-clamp-2 text-xs leading-5 text-[var(--text-muted)]">
                      {item.description}
                    </p>
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    type="button"
                    aria-pressed={isChosen}
                    onClick={() => onToggleChosen(item.id)}
                    className={`inline-flex h-8 items-center gap-1.5 rounded-lg px-3 text-xs font-semibold transition ${
                      isChosen
                        ? 'bg-[var(--brand-light)] text-[var(--brand)]'
                        : 'border border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]'
                    }`}
                  >
                    {isChosen ? <Check className="h-3.5 w-3.5" /> : null}
                    {isChosen ? '已选用' : '选用'}
                  </button>
                  <button
                    type="button"
                    aria-label={item.primary.ariaLabel}
                    onClick={() => onPrimary(item)}
                    disabled={item.primary.disabled}
                    className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)] disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {item.primary.icon ? <item.primary.icon className="h-3.5 w-3.5" /> : null}
                    {item.primary.label}
                  </button>
                </div>
              </li>
            );
          })
        )}
      </ul>

      <div className="sticky bottom-0 -mx-6 mt-auto border-t border-[var(--border)] bg-[var(--surface-1)] px-6 py-4 sm:-mx-8 sm:px-8">
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-[var(--text-muted)]">{copy.chosenHint}</p>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-9 items-center rounded-lg bg-[var(--brand)] px-4 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]"
          >
            完成选用
          </button>
        </div>
      </div>
    </SideDrawer>
  );
}
