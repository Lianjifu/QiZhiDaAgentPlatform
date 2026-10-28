/**
 * AdminMemory — 渲染 + 三层 tab 切换 + 默认短期记忆 + 策略配置入口。
 */
import { describe, expect, it, afterEach } from 'vitest';
import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { qk } from '@/api/shared/query-keys';
import { renderWithProviders, pageQueryKey } from '@/test-utils/seed';
import {
  mockL1Sessions, mockL2Facts, mockL3Entries, mockPromotions, mockRetentionPolicies,
} from './fixtures';
import MemoryPage from './index';
import PolicyDetailPage from './PolicyDetailPage';

afterEach(() => cleanup());

const seeds = [
  { key: pageQueryKey(qk.admin.memory.l1), data: mockL1Sessions },
  { key: pageQueryKey(qk.admin.memory.l2), data: mockL2Facts },
  { key: pageQueryKey(qk.admin.memory.l3), data: mockL3Entries },
  { key: pageQueryKey(qk.admin.memory.promotions), data: mockPromotions },
  { key: pageQueryKey(qk.admin.memory.policies), data: mockRetentionPolicies },
];

function renderPage() {
  return renderWithProviders(<MemoryPage />, {
    initialEntries: ['/admin/memory'],
    seeds,
  });
}

function renderApp() {
  return renderWithProviders(
    <Routes>
      <Route path="/admin/memory" element={<MemoryPage />} />
      <Route path="/admin/memory/policies/:id" element={<PolicyDetailPage />} />
    </Routes>,
    {
      initialEntries: ['/admin/memory'],
      seeds: [
        ...seeds,
        { key: pageQueryKey([...qk.admin.memory.policies, '短期记忆']), data: mockRetentionPolicies[0] },
        { key: pageQueryKey([...qk.admin.memory.policies, '长期记忆']), data: mockRetentionPolicies[1] },
      ],
    },
  );
}

describe('AdminMemory', () => {
  it('渲染 hero + 三层标签 + 默认短期记忆', () => {
    renderPage();
    expect(screen.getByText(/管理会话记忆和长期记忆/)).toBeTruthy();
    expect(screen.getByText('最近 7 天')).toBeTruthy();
    const nav = screen.getByLabelText('子模块导航');
    expect(within(nav).getByRole('button', { name: /短期记忆/ })).toBeTruthy();
    expect(within(nav).getByRole('button', { name: /长期记忆/ })).toBeTruthy();
    expect(within(nav).getByRole('button', { name: /知识记忆/ })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /记忆总览/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /保留策略与评测/ })).toBeNull();
    expect(screen.getByRole('button', { name: /策略配置/ })).toBeTruthy();
    expect(screen.getByText('全部 flush')).toBeTruthy();
  });

  it('默认 L1 tab 显示会话列表', () => {
    renderPage();
    expect(screen.getByText('sess-001')).toBeTruthy();
    expect(screen.getByRole('button', { name: /查看 sess-001 详情/ })).toBeTruthy();
    expect(screen.getAllByRole('button', { name: /立即 flush/ }).length).toBeGreaterThan(0);
  });

  it('切换到 L2 tab 显示事实卡片', async () => {
    renderPage();
    const nav = screen.getByLabelText('子模块导航');
    within(nav).getByRole('button', { name: /长期记忆/ }).click();
    await waitFor(() => {
      expect(screen.getByText('答复风格')).toBeTruthy();
    });
  });

  it('切换到 L3 tab 显示知识卡片', async () => {
    renderPage();
    const nav = screen.getByLabelText('子模块导航');
    within(nav).getByRole('button', { name: /知识记忆/ }).click();
    await waitFor(() => {
      expect(screen.getByText('业务术语对照表')).toBeTruthy();
    });
  });

  it('策略配置进入当前层策略详情', async () => {
    renderApp();
    fireEvent.click(screen.getByRole('button', { name: /策略配置/ }));
    await waitFor(() => {
      expect(screen.getByRole('link', { name: /返回记忆管理/ })).toBeTruthy();
    });
    expect(screen.getByText('策略参数')).toBeTruthy();
  });

  it('切换到长期记忆后策略配置进入对应策略', async () => {
    renderApp();
    const nav = screen.getByLabelText('子模块导航');
    fireEvent.click(within(nav).getByRole('button', { name: /长期记忆/ }));
    fireEvent.click(screen.getByRole('button', { name: /策略配置/ }));
    await waitFor(() => {
      expect(screen.getByText('策略参数')).toBeTruthy();
    });
    expect(screen.getByText(/用户偏好与事实/)).toBeTruthy();
  });
});
