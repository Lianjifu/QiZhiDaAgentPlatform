/**
 * 通用资源选择器(单/多选) — agents 模块 4 个 picker(Model / Skill / Knowledge / Workflow)的底层。
 *
 * 职责:
 *   - 接 data / isLoading / error(由父调用 hook 传入,本组件不调任何 hook)
 *   - 搜索 + filter chips + 列表 + 详情预览
 *   - 已选项置顶(multi 模式),支持点击 / 双击 / 键盘
 *   - 三态:loading skeleton / error / empty
 *
 * 已知约束:
 *   - 父组件若 inline 创建 searchFields / filterChips 闭包,每次 render 都是新引用,
 *     会触发本组件过滤逻辑重跑。对中小列表(< 200)无影响,大列表再考虑 memo。
 *   - 父应负责数据刷新(ResourcePicker 自身不感知 useQuery)。
 */
import { useMemo, useState } from 'react';
import type { KeyboardEvent, ReactNode } from 'react';
import { Check, Search, X } from 'lucide-react';

export interface ResourcePickerFilterChip<T> {
  key: string;
  label: string;
  match: (item: T) => boolean;
}

export interface ResourcePickerProps<T extends { id: string }> {
  mode: 'single' | 'multi';
  data: T[] | undefined;
  isLoading: boolean;
  error?: unknown;
  queryKey?: string;
  selectedIds: string[];
  onChange: (ids: string[]) => void;
  searchFields: (item: T) => string[];
  filterChips?: ResourcePickerFilterChip<T>[];
  renderItem: (item: T, selected: boolean) => ReactNode;
  renderPreview?: (item: T) => ReactNode;
  emptyText: string;
  errorText?: string;
  placeholder?: string;
  className?: string;
  listMaxHeight?: number;
}

export function ResourcePicker<T extends { id: string }>(props: ResourcePickerProps<T>) {
  const {
    mode, data, isLoading, error,
    selectedIds, onChange,
    searchFields, filterChips,
    renderItem, renderPreview,
    emptyText, errorText, placeholder,
    className, listMaxHeight = 440,
  } = props;

  const [search, setSearch] = useState('');
  const [activeChips, setActiveChips] = useState<Set<string>>(() => new Set());
  const [previewId, setPreviewId] = useState<string | null>(null);

  const filtered = useMemo(() => {
    if (!data) return [];
    const q = search.trim().toLowerCase();
    const chips = filterChips ?? [];
    return data.filter((item) => {
      if (q) {
        const fields = searchFields(item);
        const hit = fields.some((f) => f.toLowerCase().includes(q));
        if (!hit) return false;
      }
      if (activeChips.size > 0) {
        for (const key of activeChips) {
          const chip = chips.find((c) => c.key === key);
          if (!chip || !chip.match(item)) return false;
        }
      }
      return true;
    });
  }, [data, search, activeChips, searchFields, filterChips]);

  const selectedItems = useMemo(() => {
    if (!data) return [];
    return selectedIds
      .map((id) => data.find((d) => d.id === id))
      .filter((x): x is T => Boolean(x));
  }, [data, selectedIds]);

  // single 模式:被选项也走列表(用单选 radio 高亮);multi 模式:已选项置顶 + 分隔 + 未选
  const unselectedItems = useMemo(
    () => (mode === 'single' ? filtered : filtered.filter((item) => !selectedIds.includes(item.id))),
    [filtered, selectedIds, mode],
  );
  const showSelectedSection = mode === 'multi' && selectedItems.length > 0;

  const toggleChip = (key: string) => {
    setActiveChips((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const toggle = (id: string) => {
    if (mode === 'single') {
      onChange(selectedIds.includes(id) ? [] : [id]);
      return;
    }
    if (selectedIds.includes(id)) {
      onChange(selectedIds.filter((x) => x !== id));
    } else {
      onChange([...selectedIds, id]);
    }
  };

  const remove = (id: string) => {
    onChange(selectedIds.filter((x) => x !== id));
    if (previewId === id) setPreviewId(null);
  };

  const previewItem = previewId ? data?.find((d) => d.id === previewId) ?? null : null;

  if (isLoading) {
    return <ResourcePickerSkeleton className={className} />;
  }

  if (error) {
    return (
      <div className={`rounded-2xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-700 ${className ?? ''}`}>
        <p className="font-semibold">加载失败</p>
        <p className="mt-1 text-xs">{errorText ?? (error instanceof Error ? error.message : String(error))}</p>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className={`rounded-2xl border border-dashed border-[var(--border)] bg-[var(--bg-elevated)] p-8 text-center text-sm text-[var(--text-muted)] ${className ?? ''}`}>
        {emptyText}
      </div>
    );
  }

  const showPreview = Boolean(renderPreview);

  return (
    <div className={`rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] ${className ?? ''}`}>
      <div className="border-b border-[var(--border)] p-3">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={placeholder ?? '搜索...'}
            aria-label="搜索资源"
            className="h-9 w-full rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] pl-9 pr-3 text-sm outline-none focus:border-[var(--brand)]"
          />
        </div>
        {filterChips && filterChips.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            {filterChips.map((chip) => {
              const active = activeChips.has(chip.key);
              return (
                <button
                  key={chip.key}
                  type="button"
                  onClick={() => toggleChip(chip.key)}
                  aria-pressed={active}
                  className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium transition ${
                    active
                      ? 'bg-[var(--brand)] text-white'
                      : 'bg-[var(--bg-elevated)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]'
                  }`}
                >
                  {chip.label}
                </button>
              );
            })}
            {activeChips.size > 0 && (
              <button
                type="button"
                onClick={() => setActiveChips(new Set())}
                className="ml-1 text-[10px] text-[var(--text-muted)] hover:text-[var(--brand)]"
              >
                清除筛选
              </button>
            )}
          </div>
        )}
      </div>

      <div className={`grid ${showPreview ? 'lg:grid-cols-[1fr_320px]' : ''} min-h-[280px]`}>
        <div className="overflow-y-auto p-2" style={{ maxHeight: listMaxHeight }}>
          {showSelectedSection && (
            <>
              <div className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--brand)]">
                已选 {selectedItems.length} 项
              </div>
              {selectedItems.map((item) => (
                <PickerRow
                  key={item.id}
                  item={item}
                  selected
                  mode={mode}
                  onClick={() => toggle(item.id)}
                  onPreview={() => setPreviewId(item.id)}
                  onRemove={() => remove(item.id)}
                  renderItem={renderItem}
                />
              ))}
              {unselectedItems.length > 0 && <div className="my-2 border-t border-[var(--border)]" />}
            </>
          )}

          {unselectedItems.length === 0 ? (
            showSelectedSection ? (
              <div className="mt-2 px-2 py-3 text-center text-[10px] text-[var(--text-muted)]">
                所有匹配项都已选中
              </div>
            ) : (
              <div className="px-2 py-8 text-center text-xs text-[var(--text-muted)]">没有匹配项</div>
            )
          ) : (
            unselectedItems.map((item) => (
              <PickerRow
                key={item.id}
                item={item}
                selected={selectedIds.includes(item.id)}
                mode={mode}
                onClick={() => toggle(item.id)}
                onPreview={() => setPreviewId(item.id)}
                renderItem={renderItem}
              />
            ))
          )}
        </div>

        {showPreview && (
          <div className="border-t border-[var(--border)] bg-[var(--bg-app)] p-4 lg:border-l lg:border-t-0">
            {previewItem ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">详情预览</span>
                  <button
                    type="button"
                    onClick={() => setPreviewId(null)}
                    className="grid h-6 w-6 place-items-center rounded text-[var(--text-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--text)]"
                    aria-label="关闭预览"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
                {renderPreview!(previewItem)}
              </div>
            ) : (
              <div className="grid h-full place-items-center text-center text-xs text-[var(--text-muted)]">
                <div>
                  <Search className="mx-auto mb-2 h-6 w-6 opacity-50" />
                  <p>点击列表中的项查看详情</p>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

interface PickerRowProps<T> {
  item: T;
  selected: boolean;
  mode: 'single' | 'multi';
  onClick: () => void;
  onPreview: () => void;
  onRemove?: () => void;
  renderItem: (item: T, selected: boolean) => ReactNode;
}

function PickerRow<T extends { id: string }>({
  item, selected, mode, onClick, onPreview, onRemove, renderItem,
}: PickerRowProps<T>) {
  const handleKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onClick();
    } else if (e.key === 'Tab') {
      return;
    } else if (e.key === 'Delete' || e.key === 'Backspace') {
      if (selected && onRemove) {
        e.preventDefault();
        onRemove();
      }
    }
  };
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onDoubleClick={onPreview}
      onKeyDown={handleKey}
      aria-pressed={selected}
      className={`group relative flex cursor-pointer items-center gap-2 rounded-lg border px-2 py-2 transition ${
        selected
          ? 'border-[var(--brand)] bg-[var(--brand-light)]'
          : 'border-transparent hover:border-[var(--border)] hover:bg-[var(--surface-2)]'
      }`}
    >
      <span
        aria-hidden="true"
        className={`grid h-4 w-4 shrink-0 place-items-center border ${
          selected ? 'border-[var(--brand)] bg-[var(--brand)] text-white' : 'border-[var(--border)] bg-white'
        } ${mode === 'single' ? 'rounded-full' : 'rounded'}`}
      >
        {selected && <Check className="h-3 w-3" />}
      </span>
      <div className="min-w-0 flex-1">{renderItem(item, selected)}</div>
      {onRemove && selected && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          aria-label="移除"
          className="grid h-6 w-6 shrink-0 place-items-center rounded text-[var(--text-muted)] opacity-0 hover:bg-rose-50 hover:text-rose-600 group-hover:opacity-100"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}

function ResourcePickerSkeleton({ className }: { className?: string }) {
  return (
    <div className={`rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-4 ${className ?? ''}`} role="status" aria-busy="true">
      <div className="h-9 w-full animate-pulse rounded-xl bg-[var(--bg-hover)]" />
      <div className="mt-3 space-y-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-12 w-full animate-pulse rounded-lg bg-[var(--bg-hover)]" />
        ))}
      </div>
    </div>
  );
}
