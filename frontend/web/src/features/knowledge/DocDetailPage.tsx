/**
 * 管理侧「文档详情」独立页面 — 路由 /admin/knowledge/docs/:id
 *
 * 顶部返回知识管理;头部展示文档名 + 类型 + 状态 + 关键 KPI;
 * 下方展示归属 KB / 来源数据源链接 + 评测引用(命中本 KB 的用例)+ 切片预览(chunk list)。
 * wrapper / Stat / NotFound / Skeleton 全部走 components/DetailLayout 共享件。
 */
import { useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';
import { FileText, Database, AlignLeft, TrendingUp } from 'lucide-react';
import { useKnowledgeDocs, useKnowledgeBases, useKnowledgeSources, useKnowledgeEvalCases } from './useKnowledge';
import { DOC_STATUS_BADGE, EVAL_STATUS_BADGE } from './components/Primitives';
import { DOC_TYPE_LABEL } from './components/constants';
import {
  DetailShell, DetailHeader, DetailStatGrid, DetailStat, DetailSection,
  DetailNotFound, DetailSkeleton,
} from '@/components/feedback/DetailLayout';

export default function DocDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const docsQuery = useKnowledgeDocs();
  const kbsQuery = useKnowledgeBases();
  const sourcesQuery = useKnowledgeSources();
  const evalQuery = useKnowledgeEvalCases();
  const docs = docsQuery.data ?? [];
  const kbs = kbsQuery.data ?? [];
  const sources = sourcesQuery.data ?? [];
  const evalCases = evalQuery.data ?? [];

  const doc = useMemo(() => docs.find((d) => d.id === id), [docs, id]);
  const kb = useMemo(() => doc ? kbs.find((k) => k.id === doc.kbId) : undefined, [doc, kbs]);
  const source = useMemo(() => doc?.sourceId ? sources.find((s) => s.id === doc.sourceId) : undefined, [doc, sources]);

  const matchedEvalCases = useMemo(() => {
    if (!doc) return [];
    return evalCases.filter((e) => e.actualKb === doc.kbId && e.status === 'pass').slice(0, 8);
  }, [doc, evalCases]);

  const loading = docsQuery.isLoading || kbsQuery.isLoading || sourcesQuery.isLoading;

  if (loading) {
    return (
      <DetailShell>
        <DetailSkeleton rows={3} />
      </DetailShell>
    );
  }

  if (!doc) {
    return (
      <DetailShell>
        <DetailNotFound subject="文档不存在或已被删除" />
      </DetailShell>
    );
  }

  const badge = DOC_STATUS_BADGE[doc.status];
  const typeLabel = DOC_TYPE_LABEL[doc.type];
  const chunks = doc.chunksPreview ?? [];
  const isParsing = doc.status === 'parsing' || doc.status === 'pending';
  const emptyReason = isParsing
    ? '文档正在解析,暂无切片预览'
    : chunks.length === 0
      ? '该文档暂未提供切片预览'
      : null;

  return (
    <DetailShell>
      <DetailHeader
        eyebrow={`文档 · ${typeLabel}`}
        title={doc.name}
        icon={FileText}
        badges={[{ label: badge.label, className: badge.className }]}
        subtitle={`更新于 ${doc.updatedAt}`}
      />

      <DetailStatGrid columns={3}>
        <DetailStat label="大小" value={`${(doc.sizeKb / 1024).toFixed(2)} MB`} hint={`${doc.sizeKb.toLocaleString()} KB`} />
        <DetailStat label="切片" value={doc.chunks.toLocaleString()} hint={chunks.length > 0 ? `预览前 ${chunks.length} 条` : '暂无预览'} />
        <DetailStat label="引用" value={doc.citations.toLocaleString()} hint="累计被智能体引用" />
      </DetailStatGrid>

      <DetailSection>
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--brand)]">归属知识库</p>
            {kb ? (
              <Link to={`/admin/knowledge/kbs/${kb.id}`} className="mt-1.5 block text-sm font-semibold hover:text-[var(--brand)]">
                {kb.name}
              </Link>
            ) : (
              <p className="mt-1.5 text-sm font-semibold text-[var(--text-muted)]">{doc.kbId}</p>
            )}
            <p className="mt-1 text-[11px] text-[var(--text-muted)]">文档 ID · <code className="text-[10px]">{doc.id}</code></p>
          </div>

          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--brand)]">来源数据源</p>
            {source ? (
              <Link to={`/admin/knowledge/sources/${source.id}`} className="mt-1.5 flex items-center gap-1.5 text-sm font-semibold hover:text-[var(--brand)]">
                <Database className="h-3.5 w-3.5" />
                {source.name}
              </Link>
            ) : (
              <p className="mt-1.5 text-sm font-semibold text-[var(--text-muted)]">未关联数据源</p>
            )}
            <p className="mt-1 text-[11px] text-[var(--text-muted)]">类型 · {typeLabel} · 来源同步见数据源详情</p>
          </div>
        </div>
      </DetailSection>

      <DetailSection title={`评测引用 (${matchedEvalCases.length})`} icon={TrendingUp}>
        {matchedEvalCases.length === 0 ? (
          <p className="text-xs text-[var(--text-muted)]">暂无评测命中该知识库</p>
        ) : (
          <>
            <p className="mb-3 text-[11px] text-[var(--text-muted)]">
              以下评测命中本知识库,通过实际返回说明检索效果;具体切片归属请交叉查看下方切片预览。
            </p>
            <ul className="flex flex-col gap-2">
              {matchedEvalCases.map((e) => {
                const badge = EVAL_STATUS_BADGE[e.status];
                return (
                  <li key={e.id} className="rounded-xl border border-[var(--border)] bg-[var(--bg-app)] p-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="truncate text-sm font-semibold">{e.name}</p>
                      <span className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${badge.className}`}>{badge.label}</span>
                    </div>
                    <p className="mt-1 line-clamp-1 text-[11px] text-[var(--text-muted)]">{e.query}</p>
                    <div className="mt-1.5 flex items-center gap-1.5 text-[10px] text-[var(--text-muted)]">
                      <span>MRR {(e.mrr * 100).toFixed(0)}%</span>
                      <span>·</span>
                      <span>{e.latency.toFixed(2)}s</span>
                    </div>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </DetailSection>

      <DetailSection title={`切片预览 (${chunks.length}/${doc.chunks})`} icon={AlignLeft}>
        {emptyReason ? (
          <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-[var(--border)] bg-[var(--bg-app)] py-10 text-center text-xs text-[var(--text-muted)]">
            <AlignLeft className="h-4 w-4" />
            <p>{emptyReason}</p>
          </div>
        ) : (
          <ul className="flex max-h-[640px] flex-col gap-2 overflow-y-auto pr-1">
            {chunks.map((c) => (
              <li
                key={c.index}
                className="rounded-xl border border-[var(--border)] bg-[var(--bg-app)] p-3"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-[10px] font-semibold tabular-nums text-[var(--brand)]">
                      #{String(c.index).padStart(3, '0')}
                    </p>
                    {c.heading && (
                      <p className="mt-0.5 text-sm font-semibold tracking-tight">{c.heading}</p>
                    )}
                  </div>
                  {c.citations > 0 && (
                    <span className="inline-flex shrink-0 items-center rounded-full bg-[var(--brand-soft)] px-2 py-0.5 text-[10px] font-semibold text-[var(--brand)]">
                      引用 {c.citations}
                    </span>
                  )}
                </div>
                <p className="mt-1.5 line-clamp-2 text-xs leading-relaxed text-[var(--text-secondary)]">
                  {c.snippet}
                </p>
                <p className="mt-1.5 text-[10px] text-[var(--text-muted)]">
                  {c.tokens} tokens · {c.snippet.length} 字符
                </p>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-3 text-center text-[11px] text-[var(--text-muted)]">
          {doc.chunks > chunks.length
            ? `仅展示前 ${chunks.length} 条切片,完整 ${doc.chunks} 条请在搜索或评测中检索`
            : '已展示该文档全部切片'}
        </p>
      </DetailSection>
    </DetailShell>
  );
}