/**
 * WorkflowCreatePage 测试 — 返回 link / 3 步 / 提交跳转。
 */
import { describe, expect, it, afterEach, beforeAll, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ApiClient, setApiClient } from '@qzdap/web-api';
import WorkflowCreatePage from './WorkflowCreatePage';
import WorkflowsPage from './index';
import { wrapMockHandlerWithAdminWorkflows } from './mock-handler';

const navigateMock = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

// 「创建并进入编辑器」是真的调后端建工作流 —— 用 workflows 模块的 mock handler 当 ApiClient。
const workflowsMock = wrapMockHandlerWithAdminWorkflows(async () => undefined);

beforeAll(() => {
  setApiClient(new ApiClient('', () => null, workflowsMock));
});

afterEach(() => {
  cleanup();
  navigateMock.mockReset();
});

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderCreate() {
  const qc = makeClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/admin/workflows/new']}>
        <Routes>
          <Route path="/admin/workflows" element={<WorkflowsPage />} />
          <Route path="/admin/workflows/new" element={<WorkflowCreatePage />} />
          <Route path="/admin/workflows/:id" element={<div>工作流详情占位</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('WorkflowCreatePage', () => {
  it('renders 返回 link + 标题 + 3 步文案', () => {
    renderCreate();
    expect(screen.getByRole('link', { name: /返回工作流管理/ })).toBeTruthy();
    expect(screen.getByRole('heading', { level: 1, name: '新建工作流' })).toBeTruthy();
    expect(screen.getAllByText('基本信息').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('选模板').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('确认创建').length).toBeGreaterThanOrEqual(1);
  });

  it('step 1 下一步被空名称禁用', () => {
    renderCreate();
    const next = screen.getByRole('button', { name: /下一步/ }) as HTMLButtonElement;
    expect(next.disabled).toBe(true);
    fireEvent.change(screen.getByPlaceholderText(/客户投诉自动分流/), { target: { value: '测试工作流' } });
    expect(next.disabled).toBe(false);
  });

  it('3 步流程 + 提交触发 navigate 到 /admin/workflows/:id?edit=1', async () => {
    renderCreate();
    // Step 1: 填名 → 下一步
    fireEvent.change(screen.getByPlaceholderText(/客户投诉自动分流/), { target: { value: '测试工作流' } });
    fireEvent.click(screen.getByRole('button', { name: /下一步/ }));
    // Step 2: 空白模板已默认选中,直接下一步
    expect(screen.getByText('空白工作流')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /下一步/ }));
    // Step 3: 确认页
    expect(screen.getByText(/已准备好以下工作流/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /创建并进入编辑器/ }));
    await waitFor(() => expect(navigateMock).toHaveBeenCalled(), { timeout: 2000 });
    const called = navigateMock.mock.calls[0][0] as string;
    expect(called).toMatch(/^\/admin\/workflows\/wf-.+\?edit=1$/);
  });

  it('点击返回 link 渲染 list', () => {
    renderCreate();
    fireEvent.click(screen.getByRole('link', { name: /返回工作流管理/ }));
    // list 页应至少渲染 Hero headline 「工作流管理」
    expect(screen.getByText(/ADMIN \/ 工作流管理/)).toBeTruthy();
  });
});
