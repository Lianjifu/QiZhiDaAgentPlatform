/**
 * AdminNotifications — 渠道配置：飞书 / 企业微信 / 钉钉 / Web。
 */
import { describe, expect, it, afterEach, vi } from 'vitest';
import { cleanup, fireEvent, screen, within } from '@testing-library/react';
import { renderWithProviders, pageQueryKey } from '@/test-utils/seed';
import NotificationsPage from './NotificationsPage';
import { mockChannels, mockGroups, mockWebhooks, mockEvents } from './fixtures';
import { qk } from '@/api/shared/query-keys';

const navigateMock = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

function renderPage() {
  return renderWithProviders(<NotificationsPage />, {
    initialEntries: ['/admin/notifications'],
    seeds: [
      { key: pageQueryKey([...qk.admin.notifications.root, 'channels']), data: mockChannels },
      { key: pageQueryKey([...qk.admin.notifications.root, 'webhooks']), data: mockWebhooks },
      { key: pageQueryKey([...qk.admin.notifications.root, 'groups']), data: mockGroups },
      { key: pageQueryKey([...qk.admin.notifications.root, 'events']), data: mockEvents },
    ],
  });
}

describe('AdminNotifications', () => {
  afterEach(() => {
    cleanup();
    navigateMock.mockReset();
  });

  it('renders hero without sub-module tabs', () => {
    renderPage();
    expect(screen.getByText('接入飞书、企微、钉钉和 Web。')).toBeTruthy();
    expect(screen.getByText(/ADMIN \/ 渠道配置/)).toBeTruthy();
    expect(screen.queryByLabelText('子模块导航')).toBeNull();
    expect(screen.getByRole('combobox', { name: '视图' })).toBeTruthy();
  });

  it('renders channel cards and action buttons', () => {
    renderPage();
    expect(screen.getByText('飞书 · 客服助手')).toBeTruthy();
    expect(screen.getAllByLabelText(/^查看渠道 /).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('button', { name: /导出/ }).length).toBeGreaterThan(0);
  });

  it('新建渠道按钮进入独立页面', () => {
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /新建渠道/ }));
    expect(navigateMock).toHaveBeenCalledWith('/admin/notifications/new');
  });

  it('switches to group view and opens create-group modal', async () => {
    renderPage();
    fireEvent.change(screen.getByRole('combobox', { name: '视图' }), { target: { value: 'group' } });
    fireEvent.click(screen.getByRole('button', { name: /新建组/ }));
    const dialog = await screen.findByRole('dialog', { name: '新建接收人组' });
    expect(dialog).toBeTruthy();
    fireEvent.click(within(dialog).getByRole('button', { name: '取消' }));
    expect(screen.queryByRole('dialog', { name: '新建接收人组' })).toBeNull();
  });

  it('switches through secondary views via select', () => {
    renderPage();
    fireEvent.change(screen.getByRole('combobox', { name: '视图' }), { target: { value: 'webhook' } });
    expect(screen.getByText('CRM 同步')).toBeTruthy();
    fireEvent.change(screen.getByRole('combobox', { name: '视图' }), { target: { value: 'group' } });
    expect(screen.getByText('全员运营组')).toBeTruthy();
    fireEvent.change(screen.getByRole('combobox', { name: '视图' }), { target: { value: 'channel' } });
    expect(screen.getByText('飞书 · 客服助手')).toBeTruthy();
  });

  it('filters channels by platform', () => {
    renderPage();
    fireEvent.change(screen.getByRole('combobox', { name: '类型' }), { target: { value: 'feishu' } });
    expect(screen.getByText('飞书 · 客服助手')).toBeTruthy();
    expect(screen.queryByText('Web 工作台')).toBeNull();
    fireEvent.change(screen.getByRole('combobox', { name: '类型' }), { target: { value: 'web' } });
    expect(screen.getByText('Web 工作台')).toBeTruthy();
    expect(screen.queryByText('飞书 · 客服助手')).toBeNull();
  });
});
