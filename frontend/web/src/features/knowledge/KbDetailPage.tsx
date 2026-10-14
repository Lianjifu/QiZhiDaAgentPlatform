/**
 * 管理侧「知识库详情」— 路由 /admin/knowledge/kbs/:id
 *
 * 顶栏面包屑返回知识管理;页内无返回链。
 * Header 操作 + KPI + 基础信息 + 文档 / 最近任务 / Agent 引用。
 */
import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { FileText, Tag, Hash, Users, ChevronRight, ListChecks, AlertTriangle, Pause, Play, RefreshCw, User } from 'lucide-react';
import { useKnowledgeBase, useKnowledgeDocs, useKnowledgeTasks, useToggleKbStatus, useBatchKb } from './useKnowledge';
import { KB_STATUS_BADGE, DOC_STATUS_BADGE, TASK_STATUS_BADGE, ProgressBar } from './components/Primitives';
import { DOC_TYPE_LABEL } from './components/constants';
import {
  DetailShell, DetailStatGrid, DetailStat, DetailSection, DetailField,
  DetailNotFound, DetailSkeleton,
} from './components/DetailLayout';
import { normalizeError } from '@/api/shared/http-error';

export default function KbDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const { data: kb, isLoading, isError, error } = useKnowledgeBase(id || null);
  const { data: docs = [] } = useKnowledgeDocs();
  const { data: tasks = [] } = useKnowledgeTasks();
  const [notice, setNotice] = useState<string | null>(null);

  const kbDocs = useMemo(() => docs.filter((d) => d.kbId === id), [docs, id]);

  const recentTasks = useMemo(() => {
    return tasks.filter((t) => t.kbId === id).slice(-5).reverse();
  }, [tasks, id]);

  const boundAgents: Array<{ id: string; name: string }> = [];
  const toggleKbStatus = useToggleKbStatus();
  const batchKb = useBatchKb();

  const flash = (text: string) => {
    setNotice(text);
    window.setTimeout(() => setNotice(null), 2400);
  };

  if (isLoading) {
    return (
      <DetailShell showBack={false}>
        <DetailSkeleton rows={3} />
      </DetailShell>
    );
  }

  if (isError) {
    return <DetailShell showBack={false}><p role="alert" className="rounded-xl border border-rose-300 bg-rose-50 p-4 text-sm text-rose-700">加载失败：{normalizeError(error).message}</p></DetailShell>;
  }
  if (!kb) {
    return (
      <DetailShell showBack={false}>
        <DetailNotFound subject="知识库不存在或已被删除" />
      </DetailShell>
    );
  }

  const badge = KB_STATUS_BADGE[kb.status] ?? KB_STATUS_BADGE.paused;
  const badges = [
    { label: badge.label, className: badge.className },
    { label: `可见范围 · ${kb.scope}`, className: 'bg-[var(--bg-elevated)] text-[var(--text-secondary)]' },
  ];
  const pauseLabel = kb.status === 'paused' ? '恢复' : '暂停';

  return (
    <DetailShell showBack={false}>
      <header className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="sr-only">{kb.name}</h1>
        <div className="flex flex-wrap items-center gap-2">
          {badges.map((b, idx) => (
            <span key={idx} className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${b.className}`}>
              {b.label}
            </span>
          ))}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={() => batchKb.mutate({ ids: [kb.id], action: 'rebuild' }, {
              onSuccess: () => flash(`已触发 ${kb.name} 重建索引`),
              onError: () => flash('重建索引失败'),
            })}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--border)] px-3 text-xs font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            重建索引
          </button>
          <button
            type="button"
            onClick={() => toggleKbStatus.mutate({ id: kb.id }, {
              onSuccess: (next) => flash(`已${next.status === 'paused' ? '暂停' : '恢复'} ${kb.name}`),
              onError: () => flash('状态更新失败'),
            })}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--border)] px-3 text-xs font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]"
          >
            {kb.status === 'paused' ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
            {pauseLabel}
          </button>
        </div>
      </header>

      {notice && (
        <div className="flex items-center gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          <RefreshCw className="h-4 w-4" />
          {notice}
        </div>
      )}

      <DetailStatGrid columns={4}>
        <DetailStat label="文档数" value={kb.docCount} hint={`向量 ${kb.vectorCount}`} />
        <DetailStat label="评测命中率" value={`${(kb.evalHitRate * 100).toFixed(0)}%`} />
        <DetailStat label="最近更新" value={kb.updatedAt} hint={kb.owner} />
        <DetailStat label="被 Agent 引用" value={boundAgents.length} />
      </DetailStatGrid>

      <DetailSection>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <DetailField icon={Hash} label="知识库 ID">
            <code className="text-xs">{kb.id}</code>
          </DetailField>
          <DetailField icon={User} label="负责人">
            {kb.owner}
          </DetailField>
          <DetailField icon={Tag} label="标签">
            <div className="flex flex-wrap gap-1">
              {kb.tags.map((t) => (
                <span key={t} className="rounded-md bg-[var(--bg-elevated)] px-2 py-0.5 text-[11px]">{t}</span>
              ))}
              {kb.tags.length === 0 && <span className="text-[var(--text-muted)]">无标签</span>}
            </div>
          </DetailField>
        </div>
      </DetailSection>

      <DetailSection title={`知识库文档 (${kbDocs.length})`} icon={FileText}>
        {kbDocs.length === 0 ? (
          <p className="text-xs text-[var(--text-muted)]">该知识库暂无文档</p>
        ) : (
          <ul className="flex flex-col gap-1">
            {kbDocs.map((d) => {
              const statusBadge = DOC_STATUS_BADGE[d.status];
              const typeLabel = DOC_TYPE_LABEL[d.type];
              return (
                <li key={d.id}>
                  <Link
                    to={`/admin/knowledge/docs/${d.id}`}
                    className="group flex items-center gap-3 rounded-lg border border-[var(--border)] bg-[var(--bg-app)] px-3 py-2.5 transition-colors hover:border-[var(--brand)] hover:bg-[var(--bg-elevated)]"
                  >
                    <FileText className="h-4 w-4 shrink-0 text-[var(--text-muted)] group-hover:text-[var(--brand)]" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-semibold">{d.name}</span>
                      <span className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-[var(--text-muted)]">
                        <span className="inline-flex items-center rounded bg-[var(--bg-elevated)] px-1.5 py-0.5 font-medium text-[var(--brand)]">
                          {typeLabel}
                        </span>
                        <span className={`inline-flex items-center rounded px-1.5 py-0.5 font-medium ${statusBadge.className}`}>
                          {statusBadge.label}
                        </span>
                        <span>·</span>
                        <span>{d.chunks} chunks</span>
                        <span>·</span>
                        <span>{(d.sizeKb / 1024).toFixed(2)} MB</span>
                        <span>·</span>
                        <span>{d.citations.toLocaleString()} 引用</span>
                        <span>·</span>
                        <span>更新于 {d.updatedAt}</span>
                      </span>
                    </span>
                    <ChevronRight className="h-4 w-4 shrink-0 text-[var(--text-muted)] transition-transform group-hover:translate-x-0.5 group-hover:text-[var(--brand)]" />
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </DetailSection>

      <DetailSection title={`最近任务 (${recentTasks.length})`} icon={ListChecks}>
        {recentTasks.length === 0 ? (
          <p className="text-xs text-[var(--text-muted)]">该知识库暂无任务记录</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {recentTasks.map((t) => {
              const taskBadge = TASK_STATUS_BADGE[t.status];
              return (
                <li key={t.id} className="rounded-xl border border-[var(--border)] bg-[var(--bg-app)] p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold">{t.name}</p>
                      <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">{t.startedAt} · 耗时 {t.duration}</p>
                    </div>
                    <span className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${taskBadge.className}`}>{taskBadge.label}</span>
                  </div>
                  <ProgressBar
                    value={t.progress}
                    tone={t.status === 'failed' ? 'danger' : t.status === 'success' ? 'success' : 'brand'}
                  />
                  <p className="mt-1 text-[11px] text-[var(--text-muted)]">{t.progress}% · {t.items} 项</p>
                  {t.failureReason && (
                    <p className="mt-1.5 flex items-start gap-1 text-[11px] text-rose-600 dark:text-rose-300">
                      <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
                      {t.failureReason}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </DetailSection>

      <DetailSection title={`被以下 Agent 引用 (${boundAgents.length})`} icon={Users}>
        {boundAgents.length === 0 ? (
          <p className="text-xs text-[var(--text-muted)]">暂无 Agent 引用</p>
        ) : (
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {boundAgents.map((a) => (
              <li key={a.id} className="flex items-center justify-between rounded-lg border border-[var(--border)] bg-[var(--bg-app)] px-3 py-2 text-xs">
                <span className="font-medium">{a.name}</span>
                <Link to={`/admin/agents/${a.id}`} className="text-[var(--brand)] hover:underline">查看 →</Link>
              </li>
            ))}
          </ul>
        )}
      </DetailSection>
    </DetailShell>
  );
}
