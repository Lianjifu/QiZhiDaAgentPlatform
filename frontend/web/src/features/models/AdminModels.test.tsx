/**
 * AdminModels — 对齐技能管理：无子模块 Tab，列表工具栏 + 视图筛选。
 */
import { describe, expect, it, afterEach, vi } from 'vitest';
import { cleanup, fireEvent, screen } from '@testing-library/react';
import { qk } from '@/api/shared/query-keys';
import { renderWithProviders, pageQueryKey } from '@/test-utils/seed';
import ModelsPage from './ModelsPage';
import { mockModels, mockProviders, mockRoutes, mockHealth } from './fixtures';

const navigateMock = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigateMock };
});

function renderPage() {
  return renderWithProviders(<ModelsPage />, {
    initialEntries: ['/admin/models'],
    seeds: [
      { key: pageQueryKey(qk.admin.models.list), data: mockModels },
      { key: pageQueryKey(qk.admin.models.providers), data: mockProviders },
      { key: pageQueryKey(qk.admin.models.routes), data: mockRoutes },
      { key: pageQueryKey(qk.admin.models.health), data: mockHealth },
    ],
  });
}

describe('AdminModels', () => {
  afterEach(() => {
    cleanup();
    navigateMock.mockReset();
  });

  it('renders hero without sub-module tabs', () => {
    renderPage();
    expect(screen.getByText('接入模型并配置路由。')).toBeTruthy();
    expect(screen.queryByLabelText('子模块导航')).toBeNull();
    expect(screen.getByRole('combobox', { name: '视图' })).toBeTruthy();
  });

  it('renders model cards and action buttons', () => {
    renderPage();
    expect(screen.getByText('GPT-4o')).toBeTruthy();
    expect(screen.getByText('Claude 3.5 Sonnet')).toBeTruthy();
    expect(screen.getAllByLabelText(/^查看 .* 详情$/).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('button', { name: /导出/ }).length).toBeGreaterThan(0);
  });

  it('switches to provider view via select', () => {
    renderPage();
    fireEvent.change(screen.getByRole('combobox', { name: '视图' }), { target: { value: 'provider' } });
    expect(screen.getByText('OpenAI 官方')).toBeTruthy();
    expect(screen.getByText('Anthropic Claude')).toBeTruthy();
  });

  it('新建模型按钮进入独立页面', () => {
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /新建模型/ }));
    expect(navigateMock).toHaveBeenCalledWith('/admin/models/new');
  });

  it('switches to route view and 新建路由进入独立页面', () => {
    renderPage();
    fireEvent.change(screen.getByRole('combobox', { name: '视图' }), { target: { value: 'route' } });
    fireEvent.click(screen.getByRole('button', { name: /新建路由/ }));
    expect(navigateMock).toHaveBeenCalledWith('/admin/models/routes/new');
  });

  it('switches to health view and shows health events', () => {
    renderPage();
    fireEvent.change(screen.getByRole('combobox', { name: '视图' }), { target: { value: 'health' } });
    expect(screen.getByText(/API 网关返回 502/)).toBeTruthy();
  });
});
