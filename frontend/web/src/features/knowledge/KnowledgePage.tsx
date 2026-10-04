/**
 * AdminKnowledge — 知识管理编排:Hero + 知识库 / 数据源两个一级入口。
 *
 * 文档与任务在知识库详情查看;评测走侧栏「评测中心」。
 * 详情/新建迁到独立页面(/admin/knowledge/kbs/:id、docs/:id、sources/:id、kbs/new、sources/new),
 * 本页只负责列表 + 筛选 + 批量操作。
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BookOpen, Plus, RefreshCw, Search } from 'lucide-react';
import { AdminListPagination, paginateItems } from '@/components/feedback/AdminListPagination';
import { AdminListHeader, AdminListHeaderMetrics } from '@/components/feedback/AdminListRow';
import {
  useKnowledgeBases,
  useKnowledgeSources,
  useToggleKbStatus,
  useBatchKb,
} from './useKnowledge';
import type { Kb, TabId } from './schema';
import {
  KB_STATUS_BADGE,
  TAB_ICON,
} from './components/Primitives';
import {
  TABS,
  downloadBlob,
} from './components/constants';
import KbCard from './components/KbCard';
import SourceCard from './components/SourceCard';
import { TimeRangeDropdown } from './components/TimeRangeDropdown';

export default function KnowledgePage() {
  const [tab, setTab] = useState<TabId>('kb');
  const [range, setRange] = useState<'7d' | '30d' | '90d'>('7d');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [sourceStatusFilter, setSourceStatusFilter] = useState('all');
  const [notice, setNotice] = useState<string | null>(null);
  const [selectedKbIds, setSelectedKbIds] = useState<string[]>([]);
  const [kbPage, setKbPage] = useState(1);
  const [sourcePage, setSourcePage] = useState(1);

  const navigate = useNavigate();

  const kbsQuery = useKnowledgeBases();
  const sourcesQuery = useKnowledgeSources();

  const kbs = kbsQuery.data ?? [];
  const sources = sourcesQuery.data ?? [];

  const toggleKbStatus = useToggleKbStatus();
  const batchKb = useBatchKb();

  const docCount = useMemo(() => kbs.reduce((sum, kb) => sum + kb.docCount, 0), [kbs]);

  const visibleKbs = useMemo(() => {
    const q = search.trim().toLowerCase();
    return kbs.filter((k) => {
      if (statusFilter !== 'all' && k.status !== statusFilter) return false;
      if (q && !k.name.toLowerCase().includes(q) && !k.tags.some((t) => t.toLowerCase().includes(q))) return false;
      return true;
    });
  }, [kbs, search, statusFilter]);

  const visibleSources = useMemo(() => {
    const q = search.trim().toLowerCase();
    return sources.filter((s) => {
      if (sourceStatusFilter !== 'all' && s.status !== sourceStatusFilter) return false;
      if (q && !s.name.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [sources, search, sourceStatusFilter]);

  const kbPageItems = useMemo(() => paginateItems(visibleKbs, kbPage), [visibleKbs, kbPage]);
  const sourcePageItems = useMemo(() => paginateItems(visibleSources, sourcePage), [visibleSources, sourcePage]);

  const flash = (text: string) => {
    setNotice(text);
    window.setTimeout(() => setNotice(null), 2400);
  };

  useEffect(() => { setKbPage(1); }, [search, statusFilter]);
  useEffect(() => { setSourcePage(1); }, [search, sourceStatusFilter]);

  const toggleSelectKb = (id: string) =>
    setSelectedKbIds((prev) => (prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]));

  const handleTogglePause = (kb: Kb) => {
    toggleKbStatus.mutate(
      { id: kb.id },
      {
        onSuccess: (data) => flash(`已切换状态:${KB_STATUS_BADGE[data.status].label}`),
        onError: () => flash('切换失败'),
      },
    );
  };

  const handleBatch = (action: 'rebuild' | 'pause' | 'export') => {
    if (selectedKbIds.length === 0) {
      flash('请先选择知识库');
      return;
    }
    if (action === 'export') {
      const items = kbs.filter((k) => selectedKbIds.includes(k.id));
      downloadBlob(`kb-export-${Date.now()}.json`, JSON.stringify(items, null, 2));
      flash(`已导出 ${items.length} 个知识库`);
      return;
    }
    batchKb.mutate(
      { ids: selectedKbIds, action },
      {
        onSuccess: () => flash(`${action === 'rebuild' ? '重建' : '暂停'} ${selectedKbIds.length} 个知识库`),
        onError: () => flash('操作失败'),
      },
    );
  };

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-10">
      <section className="relative overflow-hidden rounded-[28px] border border-[var(--border)] bg-[var(--surface-1)] px-6 py-8 shadow-[var(--shadow-sm)] sm:px-8">
        <div aria-hidden="true" className="pointer-events-none absolute right-0 top-0 h-full w-1/2 bg-[radial-gradient(circle_at_top_right,var(--brand-light),transparent_68%)]" />
        <div className="relative">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--brand)]">ADMIN / 知识管理</p>
          <h2 className="mt-3 text-2xl font-semibold tracking-tight sm:text-3xl xl:text-4xl">把企业知识资产管起来。</h2>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-[var(--text-muted)]">{kbs.length} 个知识库 · {docCount.toLocaleString()} 篇文档 · {sources.length} 个数据源。</p>
        </div>
      </section>

      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border)]">
        <nav aria-label="子模块导航" className="flex flex-wrap items-center gap-1">
          {TABS.map((t) => {
            const Icon = TAB_ICON[t.id] ?? BookOpen;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                aria-pressed={tab === t.id}
                className={`inline-flex items-center gap-1.5 border-b-2 px-3 py-2.5 text-xs font-semibold transition ${tab === t.id ? 'border-[var(--brand)] text-[var(--brand)]' : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--brand)]'}`}
              >
                <Icon className="h-4 w-4" />
                {t.label}
              </button>
            );
          })}
        </nav>
        <TimeRangeDropdown value={range} onChange={setRange} />
      </div>

      {notice && (
        <div className="flex items-center gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          <RefreshCw className="h-4 w-4" />
          {notice}
        </div>
      )}

      {tab === 'kb' && (
        <section className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
          <ListToolbar
            search={search}
            onSearch={setSearch}
            searchLabel="搜索知识库"
            placeholder="搜索名称 / 标签…"
            status={statusFilter}
            onStatus={setStatusFilter}
            statusOptions={[
              { value: 'all', label: '全部状态' },
              { value: 'indexed', label: '已索引' },
              { value: 'indexing', label: '索引中' },
              { value: 'paused', label: '已暂停' },
              { value: 'failed', label: '失败' },
            ]}
            countLabel={`${visibleKbs.length} 个`}
            actionLabel="新建知识库"
            onAction={() => navigate('/admin/knowledge/kbs/new')}
          />
          {selectedKbIds.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 border-b border-[var(--border)] bg-[var(--bg-elevated)] px-5 py-2.5 text-xs sm:px-7">
              <span className="font-semibold text-[var(--text-secondary)]">已选 {selectedKbIds.length} 个</span>
              <button type="button" onClick={() => handleBatch('rebuild')} className="rounded-md border border-[var(--border)] px-2.5 py-1 hover:border-[var(--brand)] hover:text-[var(--brand)]">批量重建</button>
              <button type="button" onClick={() => handleBatch('pause')} className="rounded-md border border-[var(--border)] px-2.5 py-1 hover:border-[var(--brand)] hover:text-[var(--brand)]">批量暂停</button>
              <button type="button" onClick={() => handleBatch('export')} className="rounded-md border border-[var(--border)] px-2.5 py-1 hover:border-[var(--brand)] hover:text-[var(--brand)]">批量导出</button>
              <button type="button" onClick={() => setSelectedKbIds([])} className="rounded-md border border-[var(--border)] px-2.5 py-1 hover:border-[var(--brand)] hover:text-[var(--brand)]">清空选择</button>
            </div>
          )}
          <AdminListHeader hasStar={false} metrics={<AdminListHeaderMetrics labels={['文档', '向量']} />} />
          <div className="divide-y divide-[var(--border)]">
            {kbPageItems.slice.map((kb) => (
              <KbCard
                key={kb.id}
                kb={kb}
                selected={selectedKbIds.includes(kb.id)}
                onToggleSelect={toggleSelectKb}
                onOpen={(k) => navigate(`/admin/knowledge/kbs/${k.id}`)}
                onTogglePause={handleTogglePause}
              />
            ))}
          </div>
          <AdminListPagination
            page={kbPageItems.safePage}
            totalPages={kbPageItems.totalPages}
            total={kbPageItems.total}
            pageStart={kbPageItems.pageStart}
            pageEnd={kbPageItems.pageEnd}
            onPageChange={setKbPage}
          />
        </section>
      )}

      {tab === 'sources' && (
        <section className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
          <ListToolbar
            search={search}
            onSearch={setSearch}
            searchLabel="搜索数据源"
            placeholder="搜索数据源…"
            status={sourceStatusFilter}
            onStatus={setSourceStatusFilter}
            statusOptions={[
              { value: 'all', label: '全部状态' },
              { value: 'online', label: '在线' },
              { value: 'syncing', label: '同步中' },
              { value: 'error', label: '异常' },
              { value: 'paused', label: '已暂停' },
            ]}
            countLabel={`${visibleSources.length} 个`}
            actionLabel="新增数据源"
            onAction={() => navigate('/admin/knowledge/sources/new')}
          />
          <AdminListHeader hasCheckbox={false} hasStar={false} metrics={<AdminListHeaderMetrics labels={['条目', '最近同步']} />} />
          <div className="divide-y divide-[var(--border)]">
            {sourcePageItems.slice.map((s) => (
              <SourceCard
                key={s.id}
                source={s}
                onOpen={(src) => navigate(`/admin/knowledge/sources/${src.id}`)}
                onSync={() => flash(`已触发 ${s.name} 同步`)}
                onConfig={(src) => flash(`配置 ${src.name}(占位)`)}
              />
            ))}
          </div>
          <AdminListPagination
            page={sourcePageItems.safePage}
            totalPages={sourcePageItems.totalPages}
            total={sourcePageItems.total}
            pageStart={sourcePageItems.pageStart}
            pageEnd={sourcePageItems.pageEnd}
            onPageChange={setSourcePage}
          />
        </section>
      )}

      <p className="text-center text-xs text-[var(--text-muted)]">本页为前端演示数据,生产环境将接入企智搭知识中台。</p>
    </div>
  );
}

function ListToolbar({
  search,
  onSearch,
  searchLabel,
  placeholder,
  status,
  onStatus,
  statusOptions,
  countLabel,
  actionLabel,
  onAction,
}: {
  search: string;
  onSearch: (value: string) => void;
  searchLabel: string;
  placeholder: string;
  status: string;
  onStatus: (value: string) => void;
  statusOptions: { value: string; label: string }[];
  countLabel: string;
  actionLabel: string;
  onAction: () => void;
}) {
  return (
    <div className="flex flex-col gap-2 border-b border-[var(--border)] px-4 py-3 sm:flex-row sm:items-center sm:px-5">
      <label className="relative min-w-0 flex-1">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-muted)]" />
        <input
          aria-label={searchLabel}
          value={search}
          onChange={(event) => onSearch(event.target.value)}
          placeholder={placeholder}
          className="h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] pl-8 pr-3 text-sm outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--brand)]"
        />
      </label>
      <div className="flex shrink-0 items-center gap-2">
        <select
          aria-label="状态"
          value={status}
          onChange={(event) => onStatus(event.target.value)}
          className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-xs outline-none focus:border-[var(--brand)]"
        >
          {statusOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
        <span className="text-xs tabular-nums text-[var(--text-muted)]">{countLabel}</span>
        <button type="button" onClick={onAction} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]">
          <Plus className="h-3.5 w-3.5" />
          {actionLabel}
        </button>
      </div>
    </div>
  );
}

