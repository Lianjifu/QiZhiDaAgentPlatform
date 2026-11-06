/**
 * L1 短期会话详情 — 路由 /admin/memory/l1/:id
 */
import { useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  Activity, Calendar, Clock, Hash, Link as LinkIcon, User,
} from 'lucide-react';
import { useL1Session } from './useMemory';
import { useL1Sessions } from './useMemory';
import {
  DetailShell, DetailHeader, DetailStatGrid, DetailStat,
  DetailSection, DetailField, DetailNotFound, DetailSkeleton,
} from '@/components/feedback/DetailLayout';
import { L1_STATUS_BADGE, LAYER_META } from './components/constants';

export default function L1DetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const decoded = useMemo(() => decodeURIComponent(id), [id]);
  const { data: session, isLoading } = useL1Session(decoded || null);
  const { data: allSessions } = useL1Sessions();
  const meta = LAYER_META.l1;
  const Icon = meta.icon;

  if (isLoading) {
    return (
      <DetailShell backTo="/admin/memory" backLabel="返回记忆管理">
        <DetailSkeleton rows={3} />
      </DetailShell>
    );
  }
  if (!session) {
    return (
      <DetailShell backTo="/admin/memory" backLabel="返回记忆管理">
        <DetailNotFound subject="短期会话不存在或已被清空" />
      </DetailShell>
    );
  }

  const status = L1_STATUS_BADGE[session.status];
  const ttlPct = session.ttlMinutes === 0 ? 0 : Math.round(((session.ttlMinutes - session.ttlRemainMin) / session.ttlMinutes) * 100);

  return (
    <DetailShell backTo="/admin/memory" backLabel="返回记忆管理">
      <DetailHeader
        eyebrow={`短期记忆 · 会话 sess-${session.id.split('-')[1]?.padStart(3, '0') ?? '000'}`}
        title={`${session.userName} ↔ ${session.agentName}`}
        icon={Icon}
        iconClass={`${meta.tone === 'info' ? 'bg-sky-50 text-sky-600 dark:bg-sky-500/15 dark:text-sky-300' : ''}`}
        subtitle={`开始 ${session.startedAt} · 最近 flush ${session.lastFlush}`}
        badges={[
          { label: status.label, className: status.className },
          { label: `TTL 剩 ${session.ttlRemainMin}/${session.ttlMinutes}m`, className: 'bg-[var(--bg-elevated)] text-[var(--text-secondary)]' },
        ]}
      />

      <DetailStatGrid columns={4}>
        <DetailStat label="缓冲条数" value={session.bufferSize} />
        <DetailStat label="累计 Tokens" value={session.tokensUsed.toLocaleString()} />
        <DetailStat label="TTL 进度" value={`${ttlPct}%`} tone={ttlPct > 80 ? 'warn' : 'info'} hint={`剩 ${session.ttlRemainMin}m`} />
        <DetailStat label="状态" value={status.label} tone={session.status === 'expired' ? 'danger' : session.status === 'paused' ? 'warn' : 'success'} />
      </DetailStatGrid>

      <DetailSection title="会话摘要" icon={Activity}>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <DetailField icon={User} label="用户">{session.userName}</DetailField>
          <DetailField icon={Activity} label="智能体">{session.agentName}</DetailField>
          <DetailField icon={Calendar} label="开始时间">{session.startedAt}</DetailField>
          <DetailField icon={Clock} label="最近 flush">{session.lastFlush}</DetailField>
        </div>
      </DetailSection>

      <DetailSection title="关联长期事实" icon={LinkIcon}>
        {(() => {
          const derived = (allSessions ?? []).filter((s) => s.id !== session.id).slice(0, 4);
          if (derived.length === 0) {
            return <p className="text-xs text-[var(--text-muted)]">暂无同会话上下文关联</p>;
          }
          return (
            <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {derived.map((s) => {
                const ss = L1_STATUS_BADGE[s.status];
                return (
                  <li key={s.id} className="flex items-center justify-between rounded-xl border border-[var(--border)] bg-[var(--bg-app)] px-3 py-2 text-xs">
                    <span className="min-w-0 flex-1 truncate">
                      <span className="font-medium">{s.userName} ↔ {s.agentName}</span>
                      <span className="ml-2 text-[var(--text-muted)]">tokens {s.tokensUsed.toLocaleString()}</span>
                    </span>
                    <Link to={`/admin/memory/l1/${s.id}`} className="text-[var(--brand)] hover:underline">查看 →</Link>
                    <span className={`ml-2 inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${ss.className}`}>{ss.label}</span>
                  </li>
                );
              })}
            </ul>
          );
        })()}
      </DetailSection>

      <DetailSection title="元数据" icon={Hash}>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <DetailField icon={Hash} label="会话 ID"><code className="text-xs">{session.id}</code></DetailField>
          <DetailField icon={Clock} label="TTL 剩余 / 总时长">{`${session.ttlRemainMin} / ${session.ttlMinutes} 分钟`}</DetailField>
        </div>
      </DetailSection>
    </DetailShell>
  );
}