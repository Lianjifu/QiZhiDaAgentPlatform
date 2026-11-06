/**
 * KbDetailPage 测试 — happy-path 渲染 + 反向引用 + 404。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fireEvent, screen, waitFor, cleanup } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { renderWithProviders, pageQueryKey } from '@/test-utils/seed';
import { qk } from '@/api/shared/query-keys';

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

/** 智能体目录 —— 「被以下 Agent 引用」从这儿反查 ✓。 */
const agents = [
  {
    id: 'a-office',
    name: '办公智能体',
    description: '办公协同助手',
    category: '办公协同',
    owner: '办公协同组',
    tags: [],
    tone: 'brand',
    status: 'published',
    version: 'v1.0',
    lastUpdate: '刚刚',
    createdAt: '2026-11-06',
    calls: 0,
    successRate: 0,
    errorRate: 0,
    avgLatencyMs: 0,
    rating: 0,
    tools: [],
    starred: false,
    visibleScope: ['部门'],
    dataAccess: '',
    versions: [],
    evaluationPassRate: 0,
    evaluationRuns: 0,
    evaluationFailedCases: 0,
    trend: [],
    prompts: { prompt: '', soul: '', agents: '', user: '', tools: '' },
    customPrompts: [],
    knowledgeRefs: [{ id: 'kb-prod', name: '产品手册 v3', scope: '公开', enabled: true }],
    memoryPolicy: { enabled: true, retentionDays: 30, scope: 'user', autoSummarize: true },
    flowRefs: [],
  },
];

function renderAt(id: string | null) {
  return renderWithProviders(
    <Routes>
      <Route path="/admin/knowledge" element={<div>KnowledgePage</div>} />
      <Route path="/admin/knowledge/kbs/:id" element={<KbDetailPage />} />
    </Routes>,
    {
      initialEntries: [id ? `/admin/knowledge/kbs/${id}` : '/admin/knowledge'],
      seeds: [{ key: pageQueryKey(qk.admin.agents.list), data: agents }],
    },
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

  it('lists the agents that reference this knowledge base', async () => {
    // 「被以下 Agent 引用」从智能体目录反查 ✓ —— 不再是那个写死的空数组 ✓
    renderAt('kb-prod');
    expect(await screen.findByText(/被以下 Agent 引用 \(1\)/)).toBeTruthy();
    expect(screen.getByText('办公智能体')).toBeTruthy();
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
