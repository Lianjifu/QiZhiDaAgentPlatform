import { describe, expect, it, afterEach } from 'vitest';
import { cleanup, screen } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { qk } from '@/api/shared/query-keys';
import { renderWithProviders, pageQueryKey } from '@/test-utils/seed';
import ChannelDetailPage from './ChannelDetailPage';
import { mockChannels, mockEvents } from './fixtures';

function renderAt(id: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/admin/notifications/:id" element={<ChannelDetailPage />} />
    </Routes>,
    {
      initialEntries: [`/admin/notifications/${id}`],
      seeds: [
        { key: pageQueryKey([...qk.admin.notifications.root, 'channels']), data: mockChannels },
        { key: pageQueryKey([...qk.admin.notifications.root, 'events']), data: mockEvents },
      ],
    },
  );
}

describe('AdminChannelDetail', () => {
  afterEach(() => cleanup());

  it('renders channel name for known id', () => {
    const channel = mockChannels[0];
    renderAt(channel.id);
    expect(screen.getByRole('heading', { level: 1, name: channel.name })).toBeTruthy();
    expect(screen.getByRole('link', { name: /返回渠道配置/ })).toBeTruthy();
  });

  it('shows not-found when id is unknown', () => {
    renderAt('ch-unknown');
    expect(screen.getByText('渠道不存在或已被删除')).toBeTruthy();
  });
});
