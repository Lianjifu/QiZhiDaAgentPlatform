/**
 * KbDetailPage 测试 — happy-path 渲染 + 反向引用 + 404。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

vi.mock('./useKnowledge', () => ({
  useKnowledgeBase: vi.fn(),
  useKnowledgeDocs: vi.fn(),
  useKnowledgeTasks: vi.fn(),
  useToggleKbStatus: vi.fn(),
  useBatchKb: vi.fn(),
}));

import { useKnowledgeBase, useKnowledgeDocs, useKnowledgeTasks, useToggleKbStatus, useBatchKb } from './useKnowledge';
import KbDetailPage from './KbDetailPage';

/**
 * mutation 桩 —— 组件把「成功/失败」回调交给 mutate 的第二参数,
 * 桩里直接回调 onSuccess,等价于服务端返回 200。
 */
function mockMutations() {
  (useToggleKbStatus as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
    mutate: (_vars: unknown, opts?: { onSuccess?: (v: unknown) => void }) =>
      opts?.onSuccess?.({ id: 'kb-prod', status: 'paused' }),
  });
  (useBatchKb as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
    mutate: (_vars: unknown, opts?: { onSuccess?: () => void }) => opts?.onSuccess?.(),
  });
}

function renderAt(id: string | null) {
  return render(
    <MemoryRouter initialEntries={[id ? `/admin/knowledge/kbs/${id}` : '/admin/knowledge']}>
      <Routes>
        <Route path="/admin/knowledge" element={<div>KnowledgePage</div>} />
        <Route path="/admin/knowledge/kbs/:id" element={<KbDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('KbDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockMutations();
  });
  afterEach(() => cleanup());

  it('renders kb fields with documents list and actions', async () => {
    (useKnowledgeBase as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: {
        id: 'kb-prod',
        name: '产品手册 v3',
        description: '对外产品说明',
        owner: '产品团队',
        scope: '公开',
        status: 'indexed',
        docCount: 286,
        vectorCount: 18420,
        updatedAt: '今天 14:32',
        tags: ['产品', '客户'],
        tone: 'brand',
        evalHitRate: 0.94,
      },
      isLoading: false,
    });
    (useKnowledgeDocs as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [
        {
          id: 'doc-1', name: '功能说明.md', type: 'manual', kbId: 'kb-prod', sourceId: 'src-1',
          status: 'parsed', sizeKb: 24, chunks: 32, updatedAt: '今天', citations: 12,
          chunksPreview: [],
        },
        {
          id: 'doc-2', name: 'FAQ.csv', type: 'faq', kbId: 'kb-prod', sourceId: 'src-3',
          status: 'parsed', sizeKb: 18, chunks: 18, updatedAt: '昨天', citations: 8,
          chunksPreview: [],
        },
      ],
    });
    (useKnowledgeTasks as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ data: [] });

    renderAt('kb-prod');

    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1, name: '产品手册 v3' })).toBeTruthy();
    });
    expect(screen.queryByText(/对外产品说明/)).toBeNull();
    expect(screen.getByRole('button', { name: /重建索引/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: /暂停/ })).toBeTruthy();
    expect(screen.queryByRole('link', { name: /返回知识管理/ })).toBeNull();
    expect(screen.getByRole('link', { name: /功能说明\.md/ })).toBeTruthy();
    expect(screen.getByRole('link', { name: /FAQ\.csv/ })).toBeTruthy();
    expect(screen.getByText(/最近任务 \(0\)/)).toBeTruthy();
    expect(screen.queryByText(/评测用例命中/)).toBeNull();
    expect(screen.getAllByText('产品团队').length).toBeGreaterThan(0);
  });

  it('shows recent tasks with failure reason', async () => {
    (useKnowledgeBase as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: {
        id: 'kb-prod',
        name: '产品手册 v3',
        description: '对外产品说明',
        owner: '产品团队',
        scope: '公开',
        status: 'indexed',
        docCount: 286,
        vectorCount: 18420,
        updatedAt: '今天 14:32',
        tags: ['产品', '客户'],
        tone: 'brand',
        evalHitRate: 0.94,
      },
      isLoading: false,
    });
    (useKnowledgeDocs as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ data: [] });
    (useKnowledgeTasks as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [
        {
          id: 'task-1', name: '产品手册 v3 全文索引', kind: 'index', kbId: 'kb-prod', sourceId: 'src-1',
          status: 'success', progress: 100, items: 286, startedAt: '今天 14:00', duration: '32 分钟',
        },
        {
          id: 'task-x', name: '某失败任务', kind: 'reindex', kbId: 'kb-prod',
          status: 'failed', progress: 12, items: 100, startedAt: '昨天', duration: '失败',
          failureReason: '凭据过期',
        },
      ],
    });

    renderAt('kb-prod');

    await waitFor(() => {
      expect(screen.getByText(/最近任务 \(2\)/)).toBeTruthy();
    });
    expect(screen.getByText('凭据过期')).toBeTruthy();
  });

  it('flashes notice when rebuild is clicked', async () => {
    (useKnowledgeBase as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: {
        id: 'kb-prod',
        name: '产品手册 v3',
        description: '对外产品说明',
        owner: '产品团队',
        scope: '公开',
        status: 'indexed',
        docCount: 286,
        vectorCount: 18420,
        updatedAt: '今天 14:32',
        tags: ['产品'],
        tone: 'brand',
        evalHitRate: 0.94,
      },
      isLoading: false,
    });
    (useKnowledgeDocs as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ data: [] });
    (useKnowledgeTasks as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ data: [] });

    renderAt('kb-prod');
    fireEvent.click(screen.getByRole('button', { name: /重建索引/ }));
    expect(screen.getByText(/已触发 产品手册 v3 重建索引/)).toBeTruthy();
  });

  it('renders not-found when kb is missing', () => {
    (useKnowledgeBase as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ data: null, isLoading: false });
    (useKnowledgeDocs as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ data: [] });
    (useKnowledgeTasks as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ data: [] });
    renderAt('nonexistent');
    expect(screen.getByText(/知识库不存在或已被删除/)).toBeTruthy();
  });

  it('shows loading state', () => {
    (useKnowledgeBase as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ data: null, isLoading: true });
    (useKnowledgeDocs as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ data: [] });
    (useKnowledgeTasks as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ data: [] });
    renderAt('kb-prod');
    expect(document.querySelectorAll('.animate-pulse').length).toBe(4);
    expect(screen.queryByText(/知识库不存在/)).toBeNull();
  });
});
