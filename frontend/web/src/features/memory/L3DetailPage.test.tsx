/**
 * L3DetailPage（**团队知识详情** ✓）测试 — happy-path + 404。
 *
 * ⚠️ **L3 表退役了** ✓（决策 #1 ✓ —— M-47 ✓）→ 页面展示的是
 * **knowledge 的文档** ✓（切片数 ✓ —— 不是命中数 ✓）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';

vi.mock('./useMemory', () => ({
  useL3Entry: vi.fn(),
  useL3Entries: vi.fn(() => ({ data: [] })),
  useL2Facts: vi.fn(() => ({ data: [] })),
}));

/** 「引用了本团队知识库的 Agent」走 **智能体列表** ✓ —— 按知识库 id 过滤 ✓。 */
vi.mock('@/features/agents/useAgents', () => ({
  useAgentsList: vi.fn(() => ({ data: [] })),
}));

import { useL3Entry, useL3Entries, useL2Facts } from './useMemory';
import { useAgentsList } from '@/features/agents/useAgents';
import L3DetailPage from './L3DetailPage';
import { renderWithProviders } from '@/test-utils/seed';

const mockAgents = [
  { id: 'ag-1', name: '客服助手', category: '客服一组', knowledgeRefs: [{ id: 'kb-产品团队', name: '产品团队', scope: '部门', enabled: true }] },
  { id: 'ag-2', name: '研发助手', category: '研发架构', knowledgeRefs: [] },
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
    },
  );
}

describe('L3DetailPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders entry header + KPIs + 切片预览 + promoted-from + same-team', async () => {
    (useL3Entry as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: {
        id: 'k-008', team: '产品团队', title: '业务术语对照表',
        summary: '内部术语、缩写、产品代号的官方解释',
        category: '术语表', chunks: 12, updatedAt: '本周', contributor: '产品团队', status: 'published',
        kbId: 'kb-产品团队',
        chunkPreview: [{ index: 1, snippet: '内部术语、缩写、产品代号的官方解释' }],
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
        { id: 'k-7', team: '产品团队', title: '发布检查清单', summary: '...', category: '流程', chunks: 4, updatedAt: '昨天', contributor: '产品团队', status: 'published', kbId: 'kb-产品团队' },
      ],
      isLoading: false,
    });
    (useAgentsList as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ data: mockAgents, isLoading: false });

    renderAt('k-008');

    await waitFor(() => {
      expect(screen.getByText('业务术语对照表')).toBeTruthy();
    });
    expect(screen.getAllByText('已发布').length).toBeGreaterThan(0);
    expect(screen.getAllByText('术语表').length).toBeGreaterThan(0);
    // ⚠️ **切片数** ✓ —— 命中数随 L3 表一起退役了 ✓。
    expect(screen.getByText('切片数')).toBeTruthy();
    // ⚠️ **摘要与切片预览都会出现这段文字** ✓ → 用 getAllByText ✓。
    expect(screen.getAllByText(/内部术语、缩写/).length).toBeGreaterThan(0);
    expect(screen.getByText('第 1 块')).toBeTruthy();
    const promoLink = screen.getByRole('link', { name: /查看长期记忆 →/ });
    expect(promoLink.getAttribute('href')).toBe('/admin/memory/l2/f-3');
    // 引用了本团队知识库的 Agent —— 绑了同一个知识库的才算 ✓。
    expect(screen.getByText('客服助手')).toBeTruthy();
    expect(screen.queryByText('研发助手')).toBeNull();
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
