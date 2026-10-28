/**
 * AdminWorkflows — 渲染 + 状态筛选 + 卡片入口跳转(mock useNavigate)。
 */
import { describe, expect, it, afterEach, vi } from 'vitest';
import { cleanup, fireEvent, screen } from '@testing-library/react';
import { qk } from '@/api/shared/query-keys';
import { renderWithProviders, pageQueryKey } from '@/test-utils/seed';
import { mockFlows } from './fixtures';
import WorkflowsPage from './index';

const navigateMock = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

afterEach(() => {
  cleanup();
  navigateMock.mockReset();
});

function renderPage() {
  return renderWithProviders(<WorkflowsPage />, {
    seeds: [
      { key: pageQueryKey(qk.admin.workflows.list), data: mockFlows },
    ],
  });
}

describe('AdminWorkflows', () => {
  it('渲染 hero + 搜索 + 状态 + 新建工作流', () => {
    renderPage();
    expect(screen.getByText(/编排并发布可执行工作流/)).toBeTruthy();
    expect(screen.getByPlaceholderText(/搜索工作流名/)).toBeTruthy();
    expect(screen.getByRole('combobox', { name: '状态' })).toBeTruthy();
    expect(screen.getByRole('button', { name: /新建工作流/ })).toBeTruthy();
  });

  it('默认状态是全部 + 渲染 FlowCard', () => {
    renderPage();
    expect((screen.getByRole('combobox', { name: '状态' }) as HTMLSelectElement).value).toBe('all');
    expect(screen.getAllByText(/销售周报自动整理/).length).toBeGreaterThan(0);
  });

  it('新建工作流按钮 → /admin/workflows/new', () => {
    renderPage();
    screen.getByRole('button', { name: /新建工作流/ }).click();
    expect(navigateMock).toHaveBeenCalledWith('/admin/workflows/new');
  });

  it('点击卡片 → /admin/workflows/:id', () => {
    renderPage();
    const firstFlow = mockFlows[0];
    fireEvent.click(screen.getByRole('button', { name: `查看 ${firstFlow.name} 详情` }));
    expect(navigateMock).toHaveBeenCalledWith(`/admin/workflows/${firstFlow.id}`);
  });

  it('列表行无查看与添加节点', () => {
    renderPage();
    expect(screen.queryByRole('button', { name: /^查看$/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /添加节点/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /^编辑$/ })).toBeNull();
    expect(screen.getAllByRole('button', { name: /^复制$/ }).length).toBeGreaterThan(0);
  });
});
