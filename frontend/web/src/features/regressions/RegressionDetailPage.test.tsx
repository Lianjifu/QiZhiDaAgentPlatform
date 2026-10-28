/**
 * RegressionDetailPage 测试 — 路由 /admin/regressions/:id
 */
import { describe, expect, it, afterEach } from 'vitest';
import { cleanup, screen } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { qk } from '@/api/shared/query-keys';
import { renderWithProviders, pageQueryKey } from '@/test-utils/seed';
import RegressionDetailPage from './RegressionDetailPage';
import { mockRegressionTracks } from './fixtures';

function renderAt(id: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/admin/regressions/:id" element={<RegressionDetailPage />} />
    </Routes>,
    {
      initialEntries: [`/admin/regressions/${id}`],
      seeds: [
        { key: pageQueryKey(qk.admin.regressions.list), data: mockRegressionTracks },
      ],
    },
  );
}

describe('AdminRegressionDetail', () => {
  afterEach(() => cleanup());

  it('renders track name and sidebar nav for known id', () => {
    const track = mockRegressionTracks[0];
    renderAt(track.id);
    expect(screen.getByRole('heading', { level: 1, name: track.name })).toBeTruthy();
    expect(screen.getByRole('link', { name: /返回回归追踪/ })).toBeTruthy();
    expect(screen.getByLabelText('回归追踪工作区')).toBeTruthy();
  });

  it('shows not-found when id is unknown', () => {
    renderAt('track-does-not-exist');
    expect(screen.getByText('追踪不存在或已被删除')).toBeTruthy();
  });
});