/**
 * 管理侧「数据源详情」— 路由 /admin/knowledge/sources/:id
 *
 * 顶栏面包屑返回知识管理;页内无返回链。
 * Header 同步操作 + KPI + 关联知识库 / 文档 / 同步任务。
 */
import { useServerAction } from '@/services/useServerAction';
import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { FileText, ListChecks, AlertTriangle, RefreshCw } from 'lucide-react';
import { useKnowledgeSources, useKnowledgeBases, useKnowledgeDocs, useKnowledgeTasks } from './useKnowledge';
import { SOURCE_STATUS_BADGE, SOURCE_TYPE_ICON, TASK_STATUS_BADGE, DOC_STATUS_BADGE, ProgressBar } from './components/Primitives';
import { DOC_TYPE_LABEL } from './components/constants';
import {
  DetailShell, DetailHeader, DetailStatGrid, DetailStat, DetailSection,
  DetailNotFound, DetailSkeleton,
} from './components/DetailLayout';
import { normalizeError } from '@/api/shared/http-error';

export default function SourceDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const sourcesQuery = useKnowledgeSources();
  const kbsQuery = useKnowledgeBases();
  const docsQuery = useKnowledgeDocs();
  const tasksQuery = useKnowledgeTasks();
  const sources = sourcesQuery.data ?? [];
  const kbs = kbsQuery.data ?? [];
  const docs = docsQuery.data ?? [];
  const tasks = tasksQuery.data ?? [];
  const [notice, setNotice] = useState<string | null>(null);

  const server = useServerAction(setNotice);

  const source = useMemo(() => sources.find((s) => s.id === id), [sources, id]);

  const linkedKbs = useMemo(() => {
    if (!source) return [] as typeof kbs;
    const linkedDocKbIds = new Set(docs.filter((d) => d.sourceId === source.id).map((d) => d.kbId));
    return kbs
      .filter((kb) => linkedDocKbIds.has(kb.id))
      .slice()
      .sort((a, b) => {
        const aCount = docs.filter((d) => d.sourceId === source.id && d.kbId === a.id).length;
        const bCount = docs.filter((d) => d.sourceId === source.id && d.kbId === b.id).length;
        return bCount - aCount;
      });
  }, [source, docs, kbs]);

  const linkedDocs = useMemo(() => {
    if (!source) return [] as typeof docs;
    return docs.filter((d) => d.sourceId === source.id);
  }, [source, docs]);

  const linkedTasks = useMemo(() => {
    if (!source) return [] as typeof tasks;
    return tasks.filter((t) => t.sourceId === source.id).slice().reverse();
  }, [source, tasks]);

  const kbById = useMemo(() => new Map(kbs.map((k) => [k.id, k])), [kbs]);

  const loading = sourcesQuery.isLoading || kbsQuery.isLoading || docsQuery.isLoading;

  const flash = (text: string) => {
    setNotice(text);
    window.setTimeout(() => setNotice(null), 2400);
  };

  if (loading) {
    return (
      <DetailShell showBack={false}>
        <DetailSkeleton rows={3} />
      </DetailShell>
    );
  }

  if (sourcesQuery.isError || kbsQuery.isError || docsQuery.isError || tasksQuery.isError) {
    return <DetailShell showBack={false}><p role="alert" className="rounded-xl border border-rose-300 bg-rose-50 p-4 text-sm text-rose-700">加载失败：{normalizeError(sourcesQuery.error ?? kbsQuery.error ?? docsQuery.error ?? tasksQuery.error).message}</p></DetailShell>;
  }

  if (!source) {
    return (
      <DetailShell showBack={false}>
        <DetailNotFound subject="数据源不存在或已被删除" />
      </DetailShell>
    );
  }

  const badge = SOURCE_STATUS_BADGE[source.status];
  const Icon = SOURCE_TYPE_ICON[source.type];

  return (
    <DetailShell showBack={false}>
      <DetailHeader
        title={source.name}
        icon={Icon}
        badges={[{ label: badge.label, className: badge.className }]}
        actions={(
          <button
            type="button"
            onClick={() => server.mutate({ path: `/api/admin/knowledge/sources/${source.id}/sync`, success: '同步请求已提交' })}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--border)] px-3 text-xs font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            立即同步
          </button>
        )}
      />

      {notice && (
        <div className="flex items-center gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          <RefreshCw className="h-4 w-4" />
          {notice}
        </div>
      )}

      {source.lastError && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300">
          <p className="font-semibold">最近错误</p>
          <p className="mt-1 text-[11px]">{source.lastError}</p>
        </div>
      )}

      <DetailStatGrid columns={2}>
        <DetailStat label="条目数" value={source.itemCount.toLocaleString()} />
        <DetailStat label="最近同步" value={source.lastSync} />
      </DetailStatGrid>

      <DetailSection title={`关联知识库 (${linkedKbs.length})`}>
        {linkedKbs.length === 0 ? (
          <p className="text-xs text-[var(--text-muted)]">该数据源暂未通过文档绑定到任何知识库</p>
        ) : (
          <ul className="divide-y divide-[var(--border)]">
            {linkedKbs.map((kb) => {
              const linkedDocCount = docs.filter((d) => d.sourceId === source.id && d.kbId === kb.id).length;
              return (
                <li key={kb.id}>
                  <Link to={`/admin/knowledge/kbs/${kb.id}`} className="flex items-center justify-between py-2 text-sm font-medium hover:text-[var(--brand)]">
                    <span>{kb.name}</span>
                    <span className="text-[11px] text-[var(--text-muted)]">{linkedDocCount} 个文档 · {kb.docCount.toLocaleString()} 总文档</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </DetailSection>

      <DetailSection title={`全部文档 (${linkedDocs.length})`} icon={FileText}>
        {linkedDocs.length === 0 ? (
          <p className="text-xs text-[var(--text-muted)]">该数据源暂无文档挂载</p>
        ) : (
          <ul className="flex flex-col gap-1">
            {linkedDocs.map((d) => {
              const statusBadge = DOC_STATUS_BADGE[d.status];
              const typeLabel = DOC_TYPE_LABEL[d.type];
              return (
                <li key={d.id}>
                  <Link
                    to={`/admin/knowledge/docs/${d.id}`}
                    className="group flex items-center justify-between gap-3 rounded-lg border border-[var(--border)] bg-[var(--bg-app)] px-3 py-2 text-xs transition-colors hover:border-[var(--brand)] hover:bg-[var(--bg-elevated)]"
                  >
                    <span className="min-w-0 flex-1 truncate">
                      <span className="font-semibold">{d.name}</span>
                      <span className="ml-2 text-[var(--text-muted)]">{typeLabel}</span>
                    </span>
                    <span className={`inline-flex items-center rounded px-1.5 py-0.5 font-medium ${statusBadge.className}`}>
                      {statusBadge.label}
                    </span>
                    <span className="text-[var(--text-muted)] tabular-nums">{(d.sizeKb / 1024).toFixed(2)} MB</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </DetailSection>

      <DetailSection title={`同步任务历史 (${linkedTasks.length})`} icon={ListChecks}>
        {linkedTasks.length === 0 ? (
          <p className="text-xs text-[var(--text-muted)]">该数据源暂无同步任务记录</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {linkedTasks.map((t) => {
              const taskBadge = TASK_STATUS_BADGE[t.status];
              const targetKb = kbById.get(t.kbId);
              return (
                <li key={t.id} className="rounded-xl border border-[var(--border)] bg-[var(--bg-app)] p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold">{t.name}</p>
                      <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
                        目标 · {targetKb ? (
                          <Link to={`/admin/knowledge/kbs/${targetKb.id}`} className="font-medium text-[var(--brand)] hover:underline">{targetKb.name}</Link>
                        ) : t.kbId}
                        {' · '}{t.startedAt} · 耗时 {t.duration}
                      </p>
                    </div>
                    <span className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${taskBadge.className}`}>{taskBadge.label}</span>
                  </div>
                  <ProgressBar
                    value={t.progress}
                    tone={t.status === 'failed' ? 'danger' : t.status === 'success' ? 'success' : 'brand'}
                  />
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
    </DetailShell>
  );
}
