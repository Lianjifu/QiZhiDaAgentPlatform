/**
 * AdminMemory mock handler — 5 个 GET 端点;L1/L2/团队知识的状态变更 + 晋升 + 策略保存均在客户端做。
 *
 * ⚠️ **团队知识来自 knowledge** ✓ —— L3 表退役了 ✓（M-47 ✓）→
 * 这里给的是 **knowledge 的文档** ✓（与真实端点同形 ✓）。
 */
import {
  mockL1Sessions, mockL2Facts, mockL3Entries, mockMemoryTrend, mockPromotions, mockRetentionPolicies,
} from './fixtures';
import type { Doc } from '@/features/knowledge/schema';

/** 记忆页看到的团队知识 ← **knowledge 的文档** ✓。 */
const mockTeamDocs: Doc[] = mockL3Entries.map((entry) => ({
  id: entry.id,
  name: entry.title,
  type: 'manual',
  kbId: entry.kbId,
  status: 'parsed',
  sizeKb: 1,
  chunks: entry.chunks,
  chunksPreview: [{ index: 1, snippet: entry.summary, citations: 0, tokens: 8 }],
  updatedAt: entry.updatedAt,
  citations: 0,
  category: entry.category,
  publishState: entry.status,
  contributor: entry.contributor,
}));

const mockTeamBases = [
  { id: 'kb-产品团队', name: '产品团队', description: '', owner: '产品团队', scope: '部门', status: 'indexed', docCount: 1, vectorCount: 1, updatedAt: '刚刚', tags: [], tone: 'info', evalHitRate: 0 },
];

const withDelay = <T>(value: T, ms = 120) =>
  new Promise<T>((resolve) => setTimeout(() => resolve(value), ms));

export function wrapMockHandlerWithAdminMemory(fallback: (path: string, opts: any) => Promise<unknown> | unknown) {
  return async (path: string, opts: any = {}) => {
    const method = (opts?.method ?? 'GET').toUpperCase();
    if (method !== 'GET') return fallback(path, opts);
    if (path === '/api/admin/memory/l1') return withDelay(mockL1Sessions);
    if (path === '/api/admin/memory/l2') return withDelay(mockL2Facts);
    if (path === '/api/admin/knowledge/docs') return withDelay(mockTeamDocs);
    if (path === '/api/admin/knowledge/kbs') return withDelay(mockTeamBases);
    if (path === '/api/admin/memory/promotions') return withDelay(mockPromotions);
    if (path === '/api/admin/memory/policies') return withDelay(mockRetentionPolicies);
    if (path === '/api/admin/memory/trend' || path.startsWith('/api/admin/memory/trend?')) return withDelay(mockMemoryTrend);
    const policyDetailMatch = /^\/api\/admin\/memory\/policies\/(.+)$/.exec(path);
    if (policyDetailMatch) {
      const id = decodeURIComponent(policyDetailMatch[1]);
      if (id === '__noop__') return withDelay(null);
      const policy = mockRetentionPolicies.find((p) => p.label === id);
      if (!policy) throw Object.assign(new Error('policy not found'), { status: 404 });
      return withDelay(policy);
    }
    const l1DetailMatch = /^\/api\/admin\/memory\/l1\/(.+)$/.exec(path);
    if (l1DetailMatch) {
      const id = decodeURIComponent(l1DetailMatch[1]);
      if (id === '__noop__') return withDelay(null);
      const item = mockL1Sessions.find((s) => s.id === id);
      if (!item) throw Object.assign(new Error('l1 session not found'), { status: 404 });
      return withDelay(item);
    }
    const l2DetailMatch = /^\/api\/admin\/memory\/l2\/(.+)$/.exec(path);
    if (l2DetailMatch) {
      const id = decodeURIComponent(l2DetailMatch[1]);
      if (id === '__noop__') return withDelay(null);
      const item = mockL2Facts.find((f) => f.id === id);
      if (!item) throw Object.assign(new Error('l2 fact not found'), { status: 404 });
      return withDelay(item);
    }
    const teamDocMatch = /^\/api\/admin\/knowledge\/docs\/(.+)$/.exec(path);
    if (teamDocMatch) {
      const id = decodeURIComponent(teamDocMatch[1]);
      if (id === '__noop__') return withDelay(null);
      const item = mockTeamDocs.find((d) => d.id === id);
      if (!item) throw Object.assign(new Error('knowledge doc not found'), { status: 404 });
      return withDelay(item);
    }
    return fallback(path, opts);
  };
}