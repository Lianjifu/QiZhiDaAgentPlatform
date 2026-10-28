/**
 * AdminFeedback — 对齐技能管理 / 模型配置：无子模块 Tab，列表工具栏 + 视图筛选。
 */
import { describe, expect, it, afterEach, vi } from 'vitest';
import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import { qk } from '@/api/shared/query-keys';
import { renderWithProviders, pageQueryKey } from '@/test-utils/seed';
import { mockFeedbackList, mockFeedbackRules, mockFeedbackTickets, mockFeedbackTopics } from './fixtures';
import FeedbackPage from './index';

const navigateMock = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigateMock };
});

function renderPage() {
  return renderWithProviders(<FeedbackPage />, {
    seeds: [
      { key: pageQueryKey(qk.admin.feedback.list), data: mockFeedbackList },
      { key: pageQueryKey(qk.admin.feedback.tickets), data: mockFeedbackTickets },
      { key: pageQueryKey(qk.admin.feedback.topics), data: mockFeedbackTopics },
      { key: pageQueryKey(qk.admin.feedback.rules), data: mockFeedbackRules },
    ],
  });
}

describe('AdminFeedback', () => {
  afterEach(() => {
    cleanup();
    navigateMock.mockReset();
  });

  it('renders hero without sub-module tabs', async () => {
    renderPage();
    expect(screen.getByText(/收集、分诊并处理用户意见/)).toBeTruthy();
    expect(screen.queryByLabelText('子模块导航')).toBeNull();
    expect(screen.getByRole('combobox', { name: '视图' })).toBeTruthy();
    await waitFor(() => {
      expect(screen.getAllByText('王芳').length).toBeGreaterThan(0);
    });
  });

  it('renders feedback cards and action buttons', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('王芳')).toBeTruthy();
    });
    expect(screen.getAllByRole('button', { name: /^分诊$/ }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('button', { name: /^解决$/ }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('button', { name: /^删除$/ }).length).toBeGreaterThan(0);
  });

  it('switches to ticket view via select', async () => {
    renderPage();
    fireEvent.change(screen.getByRole('combobox', { name: '视图' }), { target: { value: 'ticket' } });
    await waitFor(() => {
      expect(screen.getByText('所有工单')).toBeTruthy();
    });
  });

  it('switches to topic view via select', async () => {
    renderPage();
    fireEvent.change(screen.getByRole('combobox', { name: '视图' }), { target: { value: 'topic' } });
    await waitFor(() => {
      expect(screen.getByText('主题聚类')).toBeTruthy();
    });
  });

  it('switches to rule view via select', async () => {
    renderPage();
    fireEvent.change(screen.getByRole('combobox', { name: '视图' }), { target: { value: 'rule' } });
    await waitFor(() => {
      expect(screen.getByText('反馈路由规则')).toBeTruthy();
    });
  });

  it('新建工单按钮进入独立页面', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('王芳')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: /新建工单/ }));
    expect(navigateMock).toHaveBeenCalledWith('/admin/feedback/new');
  });

  it('新建规则按钮进入独立页面', async () => {
    renderPage();
    fireEvent.change(screen.getByRole('combobox', { name: '视图' }), { target: { value: 'rule' } });
    await waitFor(() => expect(screen.getByText('反馈路由规则')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: /新建规则/ }));
    expect(navigateMock).toHaveBeenCalledWith('/admin/feedback/rules/new');
  });
});
