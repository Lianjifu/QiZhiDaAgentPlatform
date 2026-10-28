/**
 * L3DetailPage 测试 — happy-path + 404。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';

vi.mock('./useMemory', () => ({
  useL3Entry: vi.fn(),
  useL3Entries: vi.fn(() => ({ data: [] })),
  useL2Facts: vi.fn(() => ({ data: [] })),
}));

/**
 * 「被引用 Agent」走真实 HTTP 通道 —— 桩掉 api client,让请求成功返回,
 * 否则 query 报错后 useApiQuery 会把 data 抹成 undefined(组件拿不到列表)。
 */
vi.mock('@qzdap/web-api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@qzdap/web-api')>();
  return {
    ...actual,
    getApiClient: () => ({
      request: async () => mockReferencedAgents,
    }),
  };
});

import { useL3Entry, useL3Entries, useL2Facts } from './useMemory';
import L3DetailPage from './L3DetailPage';
import { renderWithProviders, pageQueryKey } from '@/test-utils/seed';

/**
 * L3DetailPage 自己用 useApiQuery 拉「被引用 Agent」——
 * key 形如 ['memory','l3',<id>,'agents'],走的是 apiQueryKey 的完整形状。
 */
const AGENTS_KEY = ['memory', 'l3', 'k-008', 'agents'] as const;

const mockReferencedAgents = [
  { id: 'ag-1', name: '客服助手', category: '客服一组' },
  { id: 'ag-2', name: '研发助手', category: '研发架构' },
];

function renderAt(id: string | null) {
  return renderWithProviders(
    <Routes>
      <Route path="/admin/memory" element={<div>MemoryPage</div>} />
      <Route path="/admin/memory/l2/:id" element={<div>L2DetailStub</div>} />
      <Route path="/admin/memory/l3/:id" element={<L3DetailPage />} />
    </Routes>,
    {
      initialEntries: [id ? `/admin/memory/l3/${id}` : '/admin/memory'],
      seeds: [
        { key: pageQueryKey(AGENTS_KEY), data: mockReferencedAgents },
      ],
    },
  );
}

describe('L3DetailPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders entry header + KPIs + hits trend + promoted-from + same-team', async () => {
    (useL3Entry as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: {
        id: 'k-008', team: '产品团队', title: '业务术语对照表',
        summary: '内部术语、缩写、产品代号的官方解释',
        category: '术语表', hits: 1280, updatedAt: '本周', contributor: '产品团队', status: 'published',
        hitsTrend: [920, 1020, 1080, 1120, 1180, 1220, 1260, 1280],
        promotedFromL2Ids: ['f-3'],
      },
      isLoading: false,
    });
    (useL2Facts as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [{ id: 'f-3', userName: '李楠', key: '禁用领域', value: '不讨论价格折扣细节', category: 'context', sourceSession: 's-2', confidence: 0.98, lastUsed: '今天', promotedAt: '昨天', status: 'confirmed', promotedToL3: true }],
      isLoading: false,
    });
    (useL3Entries as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [
        { id: 'k-7', team: '产品团队', title: '发布检查清单', summary: '...', category: '流程', hits: 96, updatedAt: '昨天', contributor: '产品团队', status: 'published' },
      ],
      isLoading: false,
    });

    renderAt('k-008');

    await waitFor(() => {
      expect(screen.getByText('业务术语对照表')).toBeTruthy();
    });
    expect(screen.getAllByText('已发布').length).toBeGreaterThan(0);
    expect(screen.getAllByText('术语表').length).toBeGreaterThan(0);
    expect(screen.getByText('1280')).toBeTruthy();
    expect(screen.getByText(/内部术语、缩写/)).toBeTruthy();
    expect(screen.getAllByText('近 8 期').length).toBeGreaterThan(0);
    const promoLink = screen.getByRole('link', { name: /查看长期记忆 →/ });
    expect(promoLink.getAttribute('href')).toBe('/admin/memory/l2/f-3');
    // 被引用 Agent —— 来自 useApiQuery(['memory','l3',id,'agents'])
    expect(screen.getByText('客服助手')).toBeTruthy();
    const viewLinks = screen.getAllByRole('link', { name: /查看 →/ });
    const agentLink = viewLinks.find((a) => a.getAttribute('href') === '/admin/agents/ag-1');
    expect(agentLink).toBeTruthy();
    const teamLink = viewLinks.find((a) => a.getAttribute('href') === '/admin/memory/l3/k-7');
    expect(teamLink).toBeTruthy();
  });

  it('renders not-found when entry is missing', () => {
    (useL3Entry as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ data: null, isLoading: false });
    renderAt('nonexistent');
    expect(screen.getByText(/团队知识不存在/)).toBeTruthy();
  });
});
