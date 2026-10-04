/**
 * MemoryPage — 三层记忆编排:短期 / 长期 / 知识。
 *
 * 总览与「保留策略与评测」tab 已去掉;当前层「策略配置」进入 /admin/memory/policies/:id。
 */
import { paginateItems } from '@/components/feedback/AdminListPagination';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Settings } from 'lucide-react';
import {
  useL1Sessions, useL2Facts, useL3Entries, useMemoryStats, usePromotions,
} from './useMemory';
import type {
  L1Session, L2Category, L2Fact, L3Entry, L3Status, MemoryRange, MemoryTabId,
} from './schema';
import { LAYER_META, TABS } from './components/constants';
import { TimeRangeDropdown } from './components/TimeRangeDropdown';
import { PromoteMemoryModal } from './components/PromoteMemoryModal';
import { L1Tab } from './components/tabs/L1Tab';
import { L2Tab } from './components/tabs/L2Tab';
import { L3Tab } from './components/tabs/L3Tab';

const EMPTY_L1: L1Session[] = [];
const EMPTY_L2: L2Fact[] = [];
const EMPTY_L3: L3Entry[] = [];

export default function MemoryPage() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<MemoryTabId>('l1');
  const [range, setRange] = useState<MemoryRange>('7d');
  const [l1Query, setL1Query] = useState('');
  const [l1StatusFilter, setL1StatusFilter] = useState<'all' | L1Session['status']>('all');

  const [l2Query, setL2Query] = useState('');
  const [l2Category, setL2Category] = useState<'all' | L2Category>('all');
  const [l2UserFilter, setL2UserFilter] = useState('all');

  const [l3Query, setL3Query] = useState('');
  const [l3TeamFilter, setL3TeamFilter] = useState('all');
  const [l3StatusFilter, setL3StatusFilter] = useState<'all' | L3Status>('all');

  const [selectedL2Ids, setSelectedL2Ids] = useState<string[]>([]);
  const [l1Page, setL1Page] = useState(1);
  const [l2Page, setL2Page] = useState(1);
  const [l3Page, setL3Page] = useState(1);
  useEffect(() => setL1Page(1), [l1Query, l1StatusFilter]);
  useEffect(() => setL2Page(1), [l2Query, l2Category, l2UserFilter]);
  useEffect(() => setL3Page(1), [l3Query, l3TeamFilter, l3StatusFilter]);
  const [promoteOpen, setPromoteOpen] = useState(false);
  const [promoteIds, setPromoteIds] = useState<string[]>([]);

  const l1QueryRemote = useL1Sessions();
  const l2QueryRemote = useL2Facts();
  const l3QueryRemote = useL3Entries();
  const remoteL1 = l1QueryRemote.data ?? EMPTY_L1;
  const remoteL2 = l2QueryRemote.data ?? EMPTY_L2;
  const remoteL3 = l3QueryRemote.data ?? EMPTY_L3;
  const remotePromotions = usePromotions().data ?? [];

  const [l1, setL1] = useState<L1Session[]>(remoteL1);
  const [l2, setL2] = useState<L2Fact[]>(remoteL2);
  const [l3, setL3] = useState<L3Entry[]>(remoteL3);
  useEffect(() => setL1(remoteL1), [l1QueryRemote.data]);
  useEffect(() => setL2(remoteL2), [l2QueryRemote.data]);
  useEffect(() => setL3(remoteL3), [l3QueryRemote.data]);

  const stats = useMemoryStats(l1, l2, l3, remotePromotions);
  const counts = useMemo(() => ({ l1: stats.l1Active, l2: stats.l2Confirmed, l3: stats.l3Published }), [stats]);
  const allUsers = useMemo(() => Array.from(new Set(l2.map((f) => f.userName))).sort(), [l2]);
  const allTeams = useMemo(() => Array.from(new Set(l3.map((k) => k.team))).sort(), [l3]);

  const filteredL1 = useMemo(() => {
    const text = l1Query.trim().toLowerCase();
    return l1.filter((s) => {
      if (l1StatusFilter !== 'all' && s.status !== l1StatusFilter) return false;
      if (text && !`${s.userName} ${s.agentName}`.toLowerCase().includes(text)) return false;
      return true;
    });
  }, [l1, l1Query, l1StatusFilter]);

  const filteredL2 = useMemo(() => {
    const text = l2Query.trim().toLowerCase();
    return l2.filter((f) => {
      if (l2Category !== 'all' && f.category !== l2Category) return false;
      if (l2UserFilter !== 'all' && f.userName !== l2UserFilter) return false;
      if (text && !`${f.key} ${f.value}`.toLowerCase().includes(text)) return false;
      return true;
    });
  }, [l2, l2Query, l2Category, l2UserFilter]);

  const filteredL3 = useMemo(() => {
    const text = l3Query.trim().toLowerCase();
    return l3.filter((k) => {
      if (l3TeamFilter !== 'all' && k.team !== l3TeamFilter) return false;
      if (l3StatusFilter !== 'all' && k.status !== l3StatusFilter) return false;
      if (text && !`${k.title} ${k.summary} ${k.category}`.toLowerCase().includes(text)) return false;
      return true;
    });
  }, [l3, l3Query, l3TeamFilter, l3StatusFilter]);

  const pagedL1 = useMemo(() => paginateItems(filteredL1, l1Page), [filteredL1, l1Page]);
  const pagedL2 = useMemo(() => paginateItems(filteredL2, l2Page), [filteredL2, l2Page]);
  const pagedL3 = useMemo(() => paginateItems(filteredL3, l3Page), [filteredL3, l3Page]);

  const flushSession = (id: string) => setL1((prev) => prev.map((s) => s.id === id ? { ...s, status: 'expired', ttlRemainMin: 0 } : s));
  const flushAll = () => setL1((prev) => prev.map((s) => s.status === 'active' ? { ...s, status: 'expired', ttlRemainMin: 0 } : s));
  const confirmFact = (id: string) => setL2((prev) => prev.map((f) => f.id === id ? { ...f, status: 'confirmed' } : f));
  const retireEntry = (id: string) => setL3((prev) => prev.map((k) => k.id === id ? { ...k, status: 'retired' } : k));
  const publishEntry = (id: string) => setL3((prev) => prev.map((k) => k.id === id ? { ...k, status: 'published' } : k));
  const toggleSelectL2 = (id: string) => setSelectedL2Ids((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
  const openPromote = (ids: string[]) => {
    if (ids.length === 0) return;
    setPromoteIds(ids);
    setPromoteOpen(true);
  };
  const submitPromote = (team: string, title: string, summary: string) => {
    const id = `k-${Date.now()}`;
    setL3((prev) => [{ id, team, title, summary, category: '综合', hits: 0, updatedAt: '刚刚', contributor: '管理员', status: 'draft' }, ...prev]);
    setL2((prev) => prev.map((f) => promoteIds.includes(f.id) ? { ...f, promotedToL3: true } : f));
    setSelectedL2Ids([]);
    setPromoteOpen(false);
  };
  const openL1 = (s: L1Session) => navigate(`/admin/memory/l1/${encodeURIComponent(s.id)}`);
  const openL2 = (f: L2Fact) => navigate(`/admin/memory/l2/${encodeURIComponent(f.id)}`);
  const openL3 = (e: L3Entry) => navigate(`/admin/memory/l3/${encodeURIComponent(e.id)}`);

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-10">
      <section className="relative overflow-hidden rounded-3xl border border-[var(--border)] bg-[var(--surface-1)] px-6 py-8 shadow-sm">
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden rounded-3xl">
          <div className="absolute right-0 top-0 h-full w-1/2 bg-[radial-gradient(circle_at_top_right,rgba(59,130,246,0.08),transparent_68%)]" />
        </div>
        <div className="relative">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--brand)]">ADMIN / 记忆管理</p>
          <h2 className="mt-3 text-2xl font-semibold tracking-tight sm:text-3xl xl:text-4xl">管理会话记忆和长期记忆。</h2>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-[var(--text-muted)]">{l1.length} 条短期会话 · {l2.length} 条长期记忆 · {l3.length} 条团队知识。</p>
        </div>
      </section>

      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border)]">
        <nav aria-label="子模块导航" className="flex flex-wrap items-center gap-1">
          {TABS.map((entry) => {
            const isActive = tab === entry.id;
            const Icon = entry.icon;
            const count = counts[entry.id];
            return (
              <button
                key={entry.id}
                type="button"
                onClick={() => setTab(entry.id)}
                aria-pressed={isActive}
                className={`inline-flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2.5 text-xs font-semibold transition ${isActive ? 'border-[var(--brand)] text-[var(--brand)]' : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--brand)]'}`}
              >
                <Icon className="h-4 w-4" />{entry.label}
                <span className={`rounded px-1.5 py-0.5 text-[10px] tabular-nums ${isActive ? 'bg-[var(--brand-light)] text-[var(--brand)]' : 'bg-[var(--bg-elevated)] text-[var(--text-muted)]'}`}>{count}</span>
              </button>
            );
          })}
        </nav>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => navigate(`/admin/memory/policies/${encodeURIComponent(LAYER_META[tab].label)}`)}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-3 text-xs font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]"
          >
            <Settings className="h-3.5 w-3.5" />
            策略配置
          </button>
          <TimeRangeDropdown value={range} onChange={setRange} />
        </div>
      </div>

      {tab === 'l1' && (
        <L1Tab
          sessions={pagedL1.slice}
          query={l1Query}
          onQuery={setL1Query}
          status={l1StatusFilter}
          onStatus={setL1StatusFilter}
          onFlushAll={flushAll}
          onFlushOne={flushSession}
          onOpen={openL1}
          pagination={{ page: pagedL1.safePage, totalPages: pagedL1.totalPages, total: pagedL1.total, pageStart: pagedL1.pageStart, pageEnd: pagedL1.pageEnd, onPageChange: setL1Page }}
        />
      )}
      {tab === 'l2' && (
        <L2Tab
          facts={pagedL2.slice}
          users={allUsers}
          selectedIds={selectedL2Ids}
          query={l2Query}
          onQuery={setL2Query}
          category={l2Category}
          onCategory={setL2Category}
          userFilter={l2UserFilter}
          onUserFilter={setL2UserFilter}
          onToggleSelect={toggleSelectL2}
          onOpen={openL2}
          onPromote={(id) => openPromote([id])}
          onConfirm={confirmFact}
          onClearSelect={() => setSelectedL2Ids([])}
          onPromoteSelected={() => openPromote(selectedL2Ids)}
          pagination={{ page: pagedL2.safePage, totalPages: pagedL2.totalPages, total: pagedL2.total, pageStart: pagedL2.pageStart, pageEnd: pagedL2.pageEnd, onPageChange: setL2Page }}
        />
      )}
      {tab === 'l3' && (
        <L3Tab
          entries={pagedL3.slice}
          teams={allTeams}
          query={l3Query}
          onQuery={setL3Query}
          teamFilter={l3TeamFilter}
          onTeamFilter={setL3TeamFilter}
          statusFilter={l3StatusFilter}
          onStatusFilter={setL3StatusFilter}
          onOpen={openL3}
          onRetire={retireEntry}
          onPublish={publishEntry}
          onCreate={() => window.alert('演示版本未提供新建表单;真实环境会打开向导')}
          pagination={{ page: pagedL3.safePage, totalPages: pagedL3.totalPages, total: pagedL3.total, pageStart: pagedL3.pageStart, pageEnd: pagedL3.pageEnd, onPageChange: setL3Page }}
        />
      )}

      <PromoteMemoryModal open={promoteOpen} factIds={promoteIds} onClose={() => setPromoteOpen(false)} onConfirm={submitPromote} />
    </div>
  );
}
