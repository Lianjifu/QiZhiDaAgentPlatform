/**
 * MemoryPage 团队知识新建 — 走真实的 useApiMutation 链路。
 *
 * ⚠️ **团队知识现在归 knowledge** ✓ —— L3 表退役了 ✓（决策 #1 ✓ —— M-47 ✓）
 * → 列表读 `/api/admin/knowledge/docs` ✓，新建写 `/api/admin/knowledge/docs` ✓。
 *
 * 这里注入一个内存 store 当 ApiClient(而不是预置 query 缓存), 因为新建是一次
 * 写操作:只有真的发出去、真的回填列表,才算验证了「按钮 → 端点 → 刷新」。
 */
import { describe, expect, it, afterEach, beforeAll } from 'vitest';
import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { ApiClient, setApiClient } from '@qzdap/web-api';
import { renderWithProviders } from '@/test-utils/seed';
import MemoryPage from './index';
import {
  mockL1Sessions, mockL2Facts, mockL3Entries, mockPromotions, mockRetentionPolicies,
} from './fixtures';
import type { Doc } from '@/features/knowledge/schema';

const calls: Array<{ method: string; path: string; body: unknown }> = [];

const bases = [
  { id: 'kb-产品团队', name: '产品团队', description: '', owner: '产品团队', scope: '部门', status: 'indexed', docCount: 1, vectorCount: 1, updatedAt: '刚刚', tags: [], tone: 'info', evalHitRate: 0 },
];

/** 记忆页看到的团队知识 ← **knowledge 的文档** ✓（同一份数据 ✓）。 */
const toDoc = (entry: (typeof mockL3Entries)[number]): Doc => ({
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
});

const store = {
  l1: [...mockL1Sessions],
  l2: [...mockL2Facts],
  docs: mockL3Entries.map(toDoc),
};

const memoryMock = async (path: string, opts: any = {}) => {
  const method = (opts?.method ?? 'GET').toUpperCase();
  if (method !== 'GET') calls.push({ method, path, body: opts?.body });
  if (method === 'GET') {
    if (path === '/api/admin/memory/l1') return store.l1;
    if (path === '/api/admin/memory/l2') return store.l2;
    if (path === '/api/admin/knowledge/docs') return store.docs;
    if (path === '/api/admin/knowledge/kbs') return bases;
    if (path === '/api/admin/memory/promotions') return mockPromotions;
    if (path === '/api/admin/memory/policies') return mockRetentionPolicies;
    return undefined;
  }
  if (method === 'POST' && path === '/api/admin/knowledge/docs') {
    const body = (opts?.body ?? {}) as Partial<Doc> & { content?: string };
    const doc: Doc = {
      id: 'k-new',
      name: body.name ?? '',
      type: 'manual',
      kbId: body.kbId ?? 'kb-产品团队',
      status: 'parsed',
      sizeKb: 1,
      chunks: 1,
      chunksPreview: [{ index: 1, snippet: body.content ?? '', citations: 0, tokens: 8 }],
      updatedAt: '刚刚',
      citations: 0,
      category: body.category ?? '流程',
      publishState: (body.publishState as Doc['publishState']) ?? 'published',
      contributor: '管理员',
    };
    store.docs = [doc, ...store.docs];
    return doc;
  }
  return undefined;
};

beforeAll(() => {
  setApiClient(new ApiClient('', () => null, memoryMock));
});

afterEach(() => {
  cleanup();
  calls.length = 0;
  store.l1 = [...mockL1Sessions];
  store.l2 = [...mockL2Facts];
  store.docs = mockL3Entries.map(toDoc);
});

function renderPage() {
  return renderWithProviders(<MemoryPage />, { initialEntries: ['/admin/memory'] });
}

async function openL3Tab() {
  const nav = screen.getByLabelText('子模块导航');
  fireEvent.click(within(nav).getByRole('button', { name: /知识记忆/ }));
  await screen.findByText('业务术语对照表');
}

describe('MemoryPage 团队知识新建', () => {
  it('打开新建对话框', async () => {
    renderPage();
    await openL3Tab();
    fireEvent.click(screen.getByRole('button', { name: '新建知识' }));
    expect(screen.getByRole('dialog', { name: '新建团队知识' })).toBeTruthy();
    expect((screen.getByPlaceholderText('例如:客服退款话术统一') as HTMLInputElement).value).toBe('');
  });

  it('标题或摘要为空时不能提交', async () => {
    renderPage();
    await openL3Tab();
    fireEvent.click(screen.getByRole('button', { name: '新建知识' }));
    const submit = screen.getByRole('button', { name: /创建/ }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    fireEvent.change(screen.getByPlaceholderText('例如:客服退款话术统一'), { target: { value: '只有标题' } });
    expect((screen.getByRole('button', { name: /创建/ }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByPlaceholderText('一句话说明这条团队知识解决了什么问题'), { target: { value: '摘要' } });
    expect((screen.getByRole('button', { name: /创建/ }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('提交后调用 POST /api/admin/knowledge/docs 并刷新列表', async () => {
    renderPage();
    await openL3Tab();
    fireEvent.click(screen.getByRole('button', { name: '新建知识' }));
    fireEvent.change(screen.getByPlaceholderText('例如:客服退款话术统一'), { target: { value: '新的团队知识' } });
    fireEvent.change(screen.getByPlaceholderText('一句话说明这条团队知识解决了什么问题'), { target: { value: '这是一条新建的团队知识' } });
    fireEvent.click(screen.getByRole('button', { name: /创建/ }));

    await waitFor(() => {
      expect(screen.getByText('已创建团队知识')).toBeTruthy();
    });
    expect(calls).toHaveLength(1);
    expect(calls[0].method).toBe('POST');
    expect(calls[0].path).toBe('/api/admin/knowledge/docs');
    expect(calls[0].body).toMatchObject({
      name: '新的团队知识',
      content: '这是一条新建的团队知识',
      publishState: 'published',
      kbId: 'kb-产品团队',
    });
    // 写成功后列表重新拉取,新条目出现
    await waitFor(() => {
      expect(screen.getByText('新的团队知识')).toBeTruthy();
    });
  });

  it('取消后不发请求', async () => {
    renderPage();
    await openL3Tab();
    fireEvent.click(screen.getByRole('button', { name: '新建知识' }));
    fireEvent.click(screen.getByRole('button', { name: '取消' }));
    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: '新建团队知识' })).toBeNull();
    });
    expect(calls).toHaveLength(0);
  });
});
