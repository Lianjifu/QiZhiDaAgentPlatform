/**
 * AdminOperations — 对齐 ModelsPage：无子模块 Tab，列表工具栏 + 视图筛选。
 */
import { describe, expect, it, afterEach } from 'vitest';
import { cleanup, fireEvent, screen } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { qk } from '@/api/shared/query-keys';
import { renderWithProviders, pageQueryKey } from '@/test-utils/seed';
import OperationsPage from './OperationsPage';
import SessionDetailPage from './SessionDetailPage';
import {
  mockIncidents, mockKindStats, mockSessions, mockSpans,
} from './fixtures';

function renderPage() {
  return renderWithProviders(
    <Routes>
      <Route path="/admin/operations" element={<OperationsPage />} />
      <Route path="/admin/operations/:id" element={<SessionDetailPage />} />
    </Routes>,
    {
    initialEntries: ['/admin/operations'],
    seeds: [
      { key: pageQueryKey(qk.admin.operations.sessions), data: mockSessions },
      { key: pageQueryKey(qk.admin.operations.spans), data: mockSpans },
      { key: pageQueryKey(qk.admin.operations.incidents), data: mockIncidents },
      { key: pageQueryKey(qk.admin.operations.kindStats), data: mockKindStats },
      { key: pageQueryKey(qk.admin.operations.summary), data: { sessions: mockSessions, spans: mockSpans, incidents: mockIncidents, kindStats: mockKindStats } },
    ],
    },
  );
}

describe('AdminOperations', () => {
  afterEach(() => cleanup());

  it('renders hero without sub-module tabs', () => {
    renderPage();
    expect(screen.getByText(/还原会话的完整调用过程/)).toBeTruthy();
    expect(screen.queryByLabelText('子模块导航')).toBeNull();
    expect(screen.getByRole('combobox', { name: '视图' })).toBeTruthy();
  });

  it('renders sessions and card action buttons', () => {
    renderPage();
    expect(screen.getByText('ss-2025-09-28-001')).toBeTruthy();
    expect(screen.getByText('ss-2025-09-28-008')).toBeTruthy();
    expect(screen.getAllByLabelText(/^查看会话 /).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('button', { name: /^导出$/ }).length).toBeGreaterThan(0);
  });

  it('navigates to session detail page when card is clicked', () => {
    renderPage();
    const card = screen.getAllByLabelText(/^查看会话 /)[0];
    fireEvent.click(card);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByRole('heading', { level: 1, name: mockSessions[0].id })).toBeTruthy();
    expect(screen.getByRole('link', { name: /返回调用链路/ })).toBeTruthy();
  });

  it('switches to incident view via select and toggles resolve', () => {
    renderPage();
    fireEvent.change(screen.getByRole('combobox', { name: '视图' }), { target: { value: 'incident' } });
    expect(screen.getByText(/GitHub MCP 鉴权失败/)).toBeTruthy();
    const resolveBtn = screen.getAllByRole('button', { name: /标记解决/ })[0];
    fireEvent.click(resolveBtn);
    expect(screen.getAllByRole('button', { name: /重新打开/ }).length).toBeGreaterThan(0);
  });

  it('toggles star and batch selection on session list', () => {
    renderPage();
    const star = screen.getAllByRole('button', { name: '收藏' })[0];
    fireEvent.click(star);
    expect(screen.getAllByRole('button', { name: '取消收藏' }).length).toBeGreaterThan(0);
    const select = screen.getAllByRole('button', { name: /^选择会话 / })[0];
    fireEvent.click(select);
    expect(screen.getByLabelText('批量操作')).toBeTruthy();
  });
});
