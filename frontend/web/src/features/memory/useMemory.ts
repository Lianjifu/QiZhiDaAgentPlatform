/**
 * AdminMemory hooks — 5 个列表查询 + stats 纯函数。
 */
import { useApiMutation, useApiQuery } from '@/services/query';
import { qk } from '@/api/shared/query-keys';
import type {
  L1Session, L2Fact, L3Entry, MemoryStats, MemoryTrend, PromotionEvent, RetentionPolicy,
} from './schema';

export function useL1Sessions() {
  return useApiQuery<L1Session[]>([...qk.admin.memory.l1], '/api/admin/memory/l1', undefined, { staleTime: 30_000 });
}

export function useL2Facts() {
  return useApiQuery<L2Fact[]>([...qk.admin.memory.l2], '/api/admin/memory/l2', undefined, { staleTime: 30_000 });
}

export function useL3Entries() {
  return useApiQuery<L3Entry[]>([...qk.admin.memory.l3], '/api/admin/memory/l3', undefined, { staleTime: 30_000 });
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
  return useApiQuery<L3Entry | null>(
    qk.admin.memory.l3Detail(id ?? 'none'),
    id ? `/api/admin/memory/l3/${encodeURIComponent(id)}` : '/api/admin/memory/l3/__noop__',
    undefined,
    { enabled: Boolean(id), staleTime: 30_000 },
  );
}

export function useMemoryStats(l1: L1Session[], l2: L2Fact[], l3: L3Entry[], events: PromotionEvent[]): MemoryStats {
  return {
    l1Active: l1.filter((s) => s.status !== 'expired').length,
    l2Confirmed: l2.filter((f) => f.status !== 'retired').length,
    l3Published: l3.filter((k) => k.status === 'published').length,
    events: events.length,
  };
}

const TREND_FALLBACK: MemoryTrend = { l1Active: [0, 0, 0, 0, 0, 0, 0, 0], l2Hits: [0, 0, 0, 0, 0, 0, 0, 0], l3Hits: [0, 0, 0, 0, 0, 0, 0, 0] };

export function useMemoryTrend(range: '7d' | '30d' | '90d') {
  return useApiQuery<MemoryTrend>(
    qk.admin.memory.trend(range),
    `/api/admin/memory/trend?range=${range}`,
    undefined,
    { staleTime: 60_000 },
  ) ?? { data: TREND_FALLBACK, isLoading: false };
}

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

export function useUpdateMemoryEntry() {
  return useApiMutation<unknown, { id: string; patch: Record<string, unknown> }>((vars) => `/api/admin/memory/l3/${encodeURIComponent(vars.id)}`, { invalidateKeys: [qk.admin.memory.root] }, 'PATCH');
}

export interface CreateL3EntryInput {
  team: string;
  title: string;
  summary: string;
  category?: string;
  status?: 'draft' | 'published';
}

export function useCreateL3Entry() {
  return useApiMutation<unknown, CreateL3EntryInput>('/api/admin/memory/l3', { invalidateKeys: [qk.admin.memory.root] }, 'POST');
}
