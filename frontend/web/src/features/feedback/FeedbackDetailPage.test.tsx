/**
 * FeedbackDetailPage 测试 — 路由 /admin/feedback/:id
 */
import { describe, expect, it, afterEach } from 'vitest';
import { cleanup, screen } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { qk } from '@/api/shared/query-keys';
import { renderWithProviders, pageQueryKey } from '@/test-utils/seed';
import FeedbackDetailPage from './FeedbackDetailPage';
import { mockFeedbackList } from './fixtures';

function renderAt(id: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/admin/feedback/:id" element={<FeedbackDetailPage />} />
    </Routes>,
    {
      initialEntries: [`/admin/feedback/${id}`],
      seeds: [
        { key: pageQueryKey(qk.admin.feedback.list), data: mockFeedbackList },
      ],
    },
  );
}

describe('AdminFeedbackDetail', () => {
  afterEach(() => cleanup());

  it('renders feedback topic header and sidebar for known id', async () => {
    const fb = mockFeedbackList[0];
    renderAt(fb.id);
    expect(screen.getByRole('heading', { level: 1, name: fb.topic })).toBeTruthy();
    expect(screen.getByRole('link', { name: /返回用户反馈/ })).toBeTruthy();
    expect(screen.getByLabelText('反馈工作区')).toBeTruthy();
  });

  it('shows not-found when id is unknown', () => {
    renderAt('fb-does-not-exist');
    expect(screen.getByText('反馈不存在或已被删除')).toBeTruthy();
  });
});