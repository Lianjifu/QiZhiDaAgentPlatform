/**
 * WorkflowDetailPage 测试 — happy-path 渲染 + 反向引用 + 404。
 */
import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

vi.mock('./useWorkflows', () => ({
  useWorkflow: vi.fn(),
  // 详情页还有「发布/保存」写操作,需要 update hook 存在
  useUpdateWorkflow: () => ({ mutate: vi.fn(), isPending: false }),
}));

beforeAll(() => {
  // React Flow 在 jsdom 下依赖 ResizeObserver 来测量容器尺寸
  if (!('ResizeObserver' in globalThis)) {
    (globalThis as unknown as { ResizeObserver: typeof ResizeObserver }).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver;
  }
});

import { useWorkflow } from './useWorkflows';
import WorkflowDetailPage from './WorkflowDetailPage';

function renderAt(id: string | null) {
  return render(
    <MemoryRouter initialEntries={[id ? `/admin/workflows/${id}` : '/admin/workflows']}>
      <Routes>
        <Route path="/admin/workflows" element={<div>WorkflowsPage</div>} />
        <Route path="/admin/workflows/:id" element={<WorkflowDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('WorkflowDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders workflow fields', async () => {
    (useWorkflow as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: {
        id: 'wf-weekly',
        name: '周报自动生成',
        description: '每周五自动汇总并发送',
        owner: '运营团队',
        scene: '运营',
        trigger: '定时触发',
        status: 'published',
        callCount: 348,
        inputs: 2,
        outputs: 1,
        createdAt: '2 月前',
        updatedAt: '今天 12:00',
        boundAgents: [],
        versions: [{ v: 'v1.0', at: '2 月前', operator: '运营团队', note: '首发' }],
        initialNodes: [],
        initialEdges: [],
      },
      isLoading: false,
    });

    renderAt('wf-weekly');

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '周报自动生成' })).toBeTruthy();
    });
    expect(screen.getByText(/每周五自动汇总并发送/)).toBeTruthy();

    // 节点类型树(左侧 aside)必须渲染 5 大组
    expect(screen.getByText('开始节点')).toBeTruthy();
    expect(screen.getByText('工具调用')).toBeTruthy();
    expect(screen.getByText('智能体调用')).toBeTruthy();
    expect(screen.getByText('控制流')).toBeTruthy();
    expect(screen.getByText('结束节点')).toBeTruthy();

    // 开始节点组默认展开,显示 4 个子项(子项名与 trigger chip 可能重名,用 getAllByText)
    expect(screen.getAllByText('用户消息触发').length).toBeGreaterThan(0);
    expect(screen.getAllByText('定时触发').length).toBeGreaterThan(0);
    expect(screen.getAllByText('事件触发').length).toBeGreaterThan(0);
    expect(screen.getAllByText('手动触发').length).toBeGreaterThan(0);

    // 返回按钮存在(aria-label)
    expect(screen.getByLabelText('返回工作流管理')).toBeTruthy();
  });

  it('renders not-found when workflow is missing', () => {
    (useWorkflow as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ data: null, isLoading: false });
    renderAt('nonexistent');
    expect(screen.getByText(/工作流不存在或已被删除/)).toBeTruthy();
  });

  it('shows loading state', () => {
    (useWorkflow as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ data: null, isLoading: true });
    renderAt('wf-weekly');
    expect(screen.getByText(/加载中/)).toBeTruthy();
  });
});