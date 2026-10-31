/**
 * L1Row / L2Card / L3Card — 三层记忆的列表行。
 */
import { ArrowUpRight, BookOpen, CheckCircle2, Pause, Play, RefreshCw } from 'lucide-react';
import {
  AdminListActions, AdminListIdentity, AdminListMetric, AdminListMetrics, AdminListRow,
  adminListActionBtn, adminListDangerBtn,
} from '@/components/feedback/AdminListRow';
import type { L1Session, L2Fact, L3Entry } from '../schema';
import { L1_STATUS_BADGE, L2_CATEGORY_LABEL, L2_STATUS_BADGE, L3_STATUS_BADGE, toneClass } from './constants';

function sessionLabel(id: string) {
  const seq = id.split('-')[1] ?? '0';
  return `sess-${seq.padStart(3, '0')}`;
}

export function L1Row({ session, onFlush, onOpen }: {
  session: L1Session; onFlush: () => void; onOpen: () => void;
}) {
  const status = L1_STATUS_BADGE[session.status];
  const label = sessionLabel(session.id);
  const progress = Math.max(0, Math.min(1, session.ttlRemainMin / session.ttlMinutes));
  return (
    <AdminListRow hasCheckbox={false} hasStar={false}>
      <div
        role="button"
        tabIndex={0}
        onClick={onOpen}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen(); } }}
        aria-label={`查看 ${label} 详情`}
        className="absolute inset-0 z-0 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--brand)]"
      />
      <AdminListIdentity>
        <div className="flex min-w-0 items-center gap-1.5">
          <h4 className="truncate text-sm font-semibold group-hover:text-[var(--brand)]">{label}</h4>
          <span className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${status.className}`}>{status.label}</span>
        </div>
        <p className="mt-0.5 truncate text-[11px] text-[var(--text-muted)]">{session.userName} · {session.agentName} · {session.startedAt}</p>
        <div className="mt-1.5 h-1 w-full max-w-[14rem] overflow-hidden rounded-full bg-[var(--bg-app)]">
          <div className={`h-full rounded-full ${progress < 0.2 ? 'bg-[var(--danger)]' : 'bg-[var(--brand)]'}`} style={{ width: `${progress * 100}%` }} />
        </div>
      </AdminListIdentity>
      <AdminListMetrics cols={4}>
        <AdminListMetric>{session.bufferSize}</AdminListMetric>
        <AdminListMetric>{(session.tokensUsed / 1000).toFixed(1)} k</AdminListMetric>
        <AdminListMetric>{session.ttlRemainMin}/{session.ttlMinutes} 分</AdminListMetric>
        <AdminListMetric>{session.lastFlush}</AdminListMetric>
      </AdminListMetrics>
      <AdminListActions>
        {session.status !== 'expired' ? (
          <button type="button" onClick={(e) => { e.stopPropagation(); onFlush(); }} className={adminListActionBtn}>
            <RefreshCw className="h-3.5 w-3.5" />立即 flush
          </button>
        ) : null}
      </AdminListActions>
    </AdminListRow>
  );
}

export function L2Card({ fact, onOpen, onPromote, onConfirm, selected, onToggle }: {
  fact: L2Fact; onOpen: () => void; onPromote: () => void; onConfirm: () => void;
  selected: boolean; onToggle: () => void;
}) {
  const status = L2_STATUS_BADGE[fact.status];
  return (
    <AdminListRow selected={selected} hasStar={false}>
      <div
        role="button"
        tabIndex={0}
        onClick={onOpen}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen(); } }}
        aria-label={`查看 ${fact.key} 详情`}
        className="absolute inset-0 z-0 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--brand)]"
      />
      <button type="button" onClick={(e) => { e.stopPropagation(); onToggle(); }} aria-label={`选择 ${fact.key}`} aria-pressed={selected} className={`relative z-10 grid h-7 w-7 place-items-center rounded-md border ${selected ? 'border-[var(--brand)] bg-[var(--brand)] text-white' : 'border-[var(--border)] bg-[var(--surface-1)] text-transparent hover:border-[var(--brand)]'}`}>
        {selected ? <CheckCircle2 className="h-3.5 w-3.5" /> : null}
      </button>
      <AdminListIdentity>
        <div className="flex min-w-0 items-center gap-1.5">
          <h4 className="truncate text-sm font-semibold group-hover:text-[var(--brand)]">{fact.key}</h4>
          <span className="hidden shrink-0 rounded-full bg-[var(--bg-elevated)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-secondary)] sm:inline">{L2_CATEGORY_LABEL[fact.category]}</span>
          <span className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${status.className}`}>
            {status.label}
            {fact.promotedToL3 && <ArrowUpRight className="h-3 w-3" />}
          </span>
        </div>
        <p className="mt-0.5 truncate text-[11px] text-[var(--text-muted)]">{fact.userName} · {fact.value}</p>
      </AdminListIdentity>
      <AdminListMetrics cols={2}>
        <AdminListMetric>{(fact.confidence * 100).toFixed(0)}%</AdminListMetric>
        <AdminListMetric>{fact.lastUsed}</AdminListMetric>
      </AdminListMetrics>
      <AdminListActions>
        {fact.status === 'pending' ? (
          <button type="button" onClick={(e) => { e.stopPropagation(); onConfirm(); }} className={adminListActionBtn}>
            <CheckCircle2 className="h-3.5 w-3.5" />确认
          </button>
        ) : null}
        {fact.status === 'confirmed' && !fact.promotedToL3 ? (
          <button type="button" onClick={(e) => { e.stopPropagation(); onPromote(); }} className={adminListActionBtn}>
            <ArrowUpRight className="h-3.5 w-3.5" />晋升 L3
          </button>
        ) : null}
      </AdminListActions>
    </AdminListRow>
  );
}

export function L3Card({ entry, onOpen, onRetire, onPublish }: {
  entry: L3Entry; onOpen: () => void; onRetire: () => void; onPublish: () => void;
}) {
  const status = L3_STATUS_BADGE[entry.status];
  const layerTone = entry.status === 'retired' ? 'warn' : entry.status === 'draft' ? 'info' : 'brand';
  return (
    <AdminListRow hasCheckbox={false} hasStar={false}>
      <div
        role="button"
        tabIndex={0}
        onClick={onOpen}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen(); } }}
        aria-label={`查看 ${entry.title} 详情`}
        className="absolute inset-0 z-0 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--brand)]"
      />
      <AdminListIdentity>
        <div className="flex min-w-0 items-center gap-1.5">
          <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-md ${toneClass[layerTone]}`}>
            <BookOpen className="h-3.5 w-3.5" />
          </span>
          <h4 className="truncate text-sm font-semibold group-hover:text-[var(--brand)]">{entry.title}</h4>
          <span className="hidden shrink-0 rounded-full bg-[var(--bg-elevated)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-secondary)] sm:inline">{entry.team}</span>
          <span className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${status.className}`}>{status.label}</span>
        </div>
        <p className="mt-0.5 truncate text-[11px] text-[var(--text-muted)]">{entry.summary}</p>
      </AdminListIdentity>
      <AdminListMetrics cols={3}>
        <AdminListMetric>{entry.category}</AdminListMetric>
        <AdminListMetric>{entry.chunks} 切片</AdminListMetric>
        <AdminListMetric>{entry.updatedAt}</AdminListMetric>
      </AdminListMetrics>
      <AdminListActions>
        {entry.status === 'draft' ? (
          <button type="button" onClick={(e) => { e.stopPropagation(); onPublish(); }} className={adminListActionBtn}>
            <Play className="h-3.5 w-3.5" />发布
          </button>
        ) : null}
        {entry.status === 'published' ? (
          <button type="button" onClick={(e) => { e.stopPropagation(); onRetire(); }} className={adminListDangerBtn}>
            <Pause className="h-3.5 w-3.5" />下线
          </button>
        ) : null}
      </AdminListActions>
    </AdminListRow>
  );
}