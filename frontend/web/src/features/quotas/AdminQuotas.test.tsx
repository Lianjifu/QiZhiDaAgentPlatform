/**
 * AdminQuotas — 对齐模型管理：无子模块 Tab，列表工具栏 + 视图筛选。
 */
import { describe, expect, it, afterEach, vi } from 'vitest';
import { cleanup, fireEvent, screen } from '@testing-library/react';
import { qk } from '@/api/shared/query-keys';
import { renderWithProviders, pageQueryKey } from '@/test-utils/seed';
import QuotasPage from './QuotasPage';
import { mockBudgets, mockDepartments, mockUsage, mockAlerts } from './fixtures';

const navigateMock = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigateMock };
});

function renderPage() {
  return renderWithProviders(<QuotasPage />, {
    initialEntries: ['/admin/quotas'],
    seeds: [
      { key: pageQueryKey([...qk.admin.quotas.root, 'budgets']), data: mockBudgets },
      { key: pageQueryKey([...qk.admin.quotas.root, 'departments']), data: mockDepartments },
      { key: pageQueryKey([...qk.admin.quotas.root, 'usage']), data: mockUsage },
      { key: pageQueryKey([...qk.admin.quotas.root, 'alerts']), data: mockAlerts },
    ],
  });
}

describe('AdminQuotas', () => {
  afterEach(() => {
    cleanup();
    navigateMock.mockReset();
  });

  it('renders hero without sub-module tabs', () => {
    renderPage();
    expect(screen.getByText('控制预算、用量和告警。')).toBeTruthy();
    expect(screen.queryByLabelText('子模块导航')).toBeNull();
    expect(screen.getByRole('combobox', { name: '视图' })).toBeTruthy();
  });

  it('renders hero totals derived from budgets fixture', () => {
    renderPage();
    expect(screen.getByText('控制预算、用量和告警。')).toBeTruthy();
    // Total budget = 1_200_000 + 320_000 + 60_000 + 40_000 = 1_620_000
    expect(screen.getAllByText(/1,620,000/).length).toBeGreaterThan(0);
  });

  it('renders budget cards and action buttons', () => {
    renderPage();
    expect(screen.getByText('2026 年企业总预算')).toBeTruthy();
    expect(screen.getAllByLabelText(/^查看预算 /).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('button', { name: /导出/ }).length).toBeGreaterThan(0);
  });

  it('新建预算按钮进入独立页面', () => {
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /新建预算/ }));
    expect(navigateMock).toHaveBeenCalledWith('/admin/quotas/new');
  });

  it('switches to alert view and 新建规则进入独立页面', () => {
    renderPage();
    fireEvent.change(screen.getByRole('combobox', { name: '视图' }), { target: { value: 'alert' } });
    fireEvent.click(screen.getByRole('button', { name: /新建规则/ }));
    expect(navigateMock).toHaveBeenCalledWith('/admin/quotas/alerts/new');
  });

  it('switches through secondary views via select', () => {
    renderPage();
    fireEvent.change(screen.getByRole('combobox', { name: '视图' }), { target: { value: 'department' } });
    expect(screen.getByText('客户成功部')).toBeTruthy();
    fireEvent.change(screen.getByRole('combobox', { name: '视图' }), { target: { value: 'usage' } });
    expect(screen.getByText('本月 Token 用量')).toBeTruthy();
    fireEvent.change(screen.getByRole('combobox', { name: '视图' }), { target: { value: 'alert' } });
    expect(screen.getByText('Token 用量月度预警')).toBeTruthy();
    fireEvent.change(screen.getByRole('combobox', { name: '视图' }), { target: { value: 'budget' } });
    expect(screen.getByText('2026 年企业总预算')).toBeTruthy();
  });
});
