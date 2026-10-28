/**
 * EvaluationDetailPage 测试 — 路由 /admin/evaluations/:id
 */
import { describe, expect, it, afterEach } from 'vitest';
import { cleanup, screen } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { qk } from '@/api/shared/query-keys';
import { renderWithProviders, pageQueryKey } from '@/test-utils/seed';
import EvaluationDetailPage from './EvaluationDetailPage';
import { mockEvalSuites } from './fixtures';

function renderAt(id: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/admin/evaluations/:id" element={<EvaluationDetailPage />} />
    </Routes>,
    {
      initialEntries: [`/admin/evaluations/${id}`],
      seeds: [
        { key: pageQueryKey(qk.admin.evaluations.list), data: mockEvalSuites },
      ],
    },
  );
}

describe('AdminEvaluationDetail', () => {
  afterEach(() => cleanup());

  it('renders suite name and sidebar nav for known id', () => {
    const suite = mockEvalSuites[0];
    renderAt(suite.id);
    expect(screen.getByRole('heading', { level: 1, name: suite.name })).toBeTruthy();
    expect(screen.getByRole('link', { name: /返回评测中心/ })).toBeTruthy();
    expect(screen.getByLabelText('评测工作区导航')).toBeTruthy();
  });

  it('shows not-found when id is unknown', () => {
    renderAt('suite-does-not-exist');
    expect(screen.getByText('套件不存在或已被删除')).toBeTruthy();
  });
});