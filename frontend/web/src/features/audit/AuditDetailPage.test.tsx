/**
 * AuditDetailPage 测试 — 路由 /admin/tool-audit/:id
 */
import { describe, expect, it, afterEach } from 'vitest';
import { cleanup, fireEvent, screen } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { qk } from '@/api/shared/query-keys';
import { renderWithProviders, pageQueryKey } from '@/test-utils/seed';
import AuditDetailPage from './AuditDetailPage';
import { mockAuditEntries, mockAuditRules } from './fixtures';

function renderAt(id: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/admin/tool-audit/:id" element={<AuditDetailPage />} />
    </Routes>,
    {
      initialEntries: [`/admin/tool-audit/${id}`],
      seeds: [
        { key: pageQueryKey(qk.admin.audit.entries), data: mockAuditEntries },
        { key: pageQueryKey(qk.admin.audit.rules), data: mockAuditRules },
      ],
    },
  );
}

describe('AuditDetailPage', () => {
  afterEach(() => cleanup());

  it('renders entry id and switches to args panel', () => {
    const entry = mockAuditEntries[0];
    renderAt(entry.id);
    expect(screen.getByRole('heading', { level: 1, name: entry.id })).toBeTruthy();
    expect(screen.getByLabelText('审计工作区')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '入参与输出' }));
    expect(screen.getAllByText(/入参/).length).toBeGreaterThan(0);
  });

  it('shows not-found when id is unknown', () => {
    renderAt('ae-does-not-exist');
    expect(screen.getByText('审计条目不存在或已被删除')).toBeTruthy();
  });
});
