/**
 * AdminMemory hooks — 5 个列表查询 + stats 纯函数。
 */
import { useApiMutation, useApiQuery } from '@/services/query';
import { qk } from '@/api/shared/query-keys';
import { useKnowledgeBases, useKnowledgeDocs } from '@/features/knowledge/useKnowledge';
import type { Doc } from '@/features/knowledge/schema';
import type {
  L1Session, L2Fact, L3Entry, MemoryStats, MemoryTrend, PromotionEvent, RetentionPolicy,
} from './schema';

export function useL1Sessions() {
  return useApiQuery<L1Session[]>([...qk.admin.memory.l1], '/api/admin/memory/l1', undefined, { staleTime: 30_000 });
}

export function useL2Facts() {
  return useApiQuery<L2Fact[]>([...qk.admin.memory.l2], '/api/admin/memory/l2', undefined, { staleTime: 30_000 });
}

/** knowledge 的文档 → **团队知识** ✓（一个团队一个知识库 ✓ —— team = 库名 ✓）。 */
function toL3Entry(doc: Doc, team: string): L3Entry {
  return {
    id: doc.id,
    team,
    title: doc.name,
    summary: doc.chunksPreview?.[0]?.snippet ?? '',
    category: doc.category ?? '',
    chunks: doc.chunks ?? 0,
    updatedAt: doc.updatedAt,
    contributor: doc.contributor ?? '',
    status: (doc.publishState ?? 'published') as L3Entry['status'],
    kbId: doc.kbId,
    chunkPreview: (doc.chunksPreview ?? []).map((c) => ({ index: c.index, snippet: c.snippet, heading: c.heading })),
    promotedFromL2Ids: doc.sourceId ? doc.sourceId.split(',').filter(Boolean) : [],
  };
}

/**
 * **团队知识** ✓ —— 数据源是 **knowledge 的文档** ✓。
 *
 * ⚠️ **L3 表退役了** ✓（决策 #1 ✓ —— M-47 ✓）→ 团队知识统一归 knowledge ✓
 * （**不是两套** ✓ —— 记忆页只是**另一个视角** ✓ —— 同一份数据 ✓）。
 */
export function useL3Entries() {
  const docs = useKnowledgeDocs();
  const kbs = useKnowledgeBases();
  const teamByKb = new Map((kbs.data ?? []).map((kb) => [kb.id, kb.name]));
  const entries = (docs.data ?? []).map((doc) => toL3Entry(doc, teamByKb.get(doc.kbId) ?? ''));
  return { ...docs, data: entries };
}

export function usePromotions() {
  return useApiQuery<PromotionEvent[]>([...qk.admin.memory.promotions], '/api/admin/memory/promotions', undefined, { staleTime: 30_000 });
}

export function useRetentionPolicies() {
  return useApiQuery<RetentionPolicy[]>([...qk.admin.memory.policies], '/api/admin/memory/policies', undefined, { staleTime: 60_000 });
}

export function useRetentionPolicy(label: string | null) {
  return useApiQuery<RetentionPolicy | null>(
    [...qk.admin.memory.policies, label ?? 'none'],
    label ? `/api/admin/memory/policies/${encodeURIComponent(label)}` : '/api/admin/memory/policies/__noop__',
    undefined,
    { enabled: Boolean(label), staleTime: 60_000 },
  );
}

export function useL1Session(id: string | null) {
  return useApiQuery<L1Session | null>(
    qk.admin.memory.l1Detail(id ?? 'none'),
    id ? `/api/admin/memory/l1/${encodeURIComponent(id)}` : '/api/admin/memory/l1/__noop__',
    undefined,
    { enabled: Boolean(id), staleTime: 30_000 },
  );
}

export function useL2Fact(id: string | null) {
  return useApiQuery<L2Fact | null>(
    qk.admin.memory.l2Detail(id ?? 'none'),
    id ? `/api/admin/memory/l2/${encodeURIComponent(id)}` : '/api/admin/memory/l2/__noop__',
    undefined,
    { enabled: Boolean(id), staleTime: 30_000 },
  );
}

export function useL3Entry(id: string | null) {
  const remote = useApiQuery<Doc | null>(
    qk.admin.memory.l3Detail(id ?? 'none'),
    id ? `/api/admin/knowledge/docs/${encodeURIComponent(id)}` : '/api/admin/knowledge/docs/__noop__',
    undefined,
    { enabled: Boolean(id), staleTime: 30_000 },
  );
  const kbs = useKnowledgeBases();
  const teamByKb = new Map((kbs.data ?? []).map((kb) => [kb.id, kb.name]));
  return {
    ...remote,
    data: remote.data ? toL3Entry(remote.data, teamByKb.get(remote.data.kbId) ?? '') : null,
  };
}

export function useMemoryStats(l1: L1Session[], l2: L2Fact[], l3: L3Entry[], events: PromotionEvent[]): MemoryStats {
  return {
    l1Active: l1.filter((s) => s.status !== 'expired').length,
    l2Confirmed: l2.filter((f) => f.status !== 'retired').length,
    l3Published: l3.filter((k) => k.status === 'published').length,
    events: events.length,
  };
}

const TREND_FALLBACK: MemoryTrend = { l1Active: [0, 0, 0, 0, 0, 0, 0, 0], l2Hits: [0, 0, 0, 0, 0, 0, 0, 0] };
/** Writes deliberately target backend endpoints; there is no client-side fallback. */
export function useFlushMemorySession() {
  return useApiMutation<unknown, { id: string }>((vars) => `/api/admin/memory/l1/${encodeURIComponent(vars.id)}/flush`, { invalidateKeys: [qk.admin.memory.root] }, 'POST');
}

export function useFlushAllMemorySessions() {
  return useApiMutation<unknown, void>('/api/admin/memory/l1/flush-all', { invalidateKeys: [qk.admin.memory.root] }, 'POST');
}

export function useUpdateMemoryFact() {
  return useApiMutation<unknown, { id: string; patch: Record<string, unknown> }>((vars) => `/api/admin/memory/l2/${encodeURIComponent(vars.id)}`, { invalidateKeys: [qk.admin.memory.root] }, 'PATCH');
}

export function usePromoteMemoryFacts() {
  return useApiMutation<unknown, { ids: string[]; team: string; title: string; summary: string }>('/api/admin/memory/l2/promote', { invalidateKeys: [qk.admin.memory.root] }, 'POST');
}

/** **发布 / 下线团队知识** ✓ —— 落点是 knowledge 的文档 ✓（L3 退役 ✓）。 */
export function useUpdateMemoryEntry() {
  return useApiMutation<unknown, { id: string; patch: Record<string, unknown> }>((vars) => `/api/admin/knowledge/docs/${encodeURIComponent(vars.id)}`, { invalidateKeys: [qk.admin.memory.root, qk.admin.knowledge.root] }, 'PATCH');
}

export interface CreateL3EntryInput {
  /** 团队 = **知识库 id** ✓（一个团队一个库 ✓ —— M-47 ✓）。 */
  kbId: string;
  name: string;
  content: string;
  type?: 'manual';
  category?: string;
  publishState?: 'draft' | 'published';
}

/** **新建团队知识** ✓ —— 落点是 knowledge 的文档 ✓（请求体就是文档的形状 ✓）。 */
export function useCreateL3Entry() {
  return useApiMutation<unknown, CreateL3EntryInput>(
    '/api/admin/knowledge/docs',
    { invalidateKeys: [qk.admin.memory.root, qk.admin.knowledge.root] },
    'POST',
  );
}
