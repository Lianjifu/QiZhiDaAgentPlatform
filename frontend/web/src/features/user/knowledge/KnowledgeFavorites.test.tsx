/**
 * 收藏状态由后端按用户存 ✓ —— 刷新后要按服务端返回的 favorited 恢复标记 ✓
 * （否则收藏只活在浏览器内存里 ✗ —— 换个设备就没了 ✗）。
 *
 * 这个文件**单独 mock API** ✓ —— 不动 Knowledge.test.tsx ✓（那份依赖「查询失败
 * → 页面空」这个前提 ✓ —— 换了 mock 语义就变了 ✗）。
 */
import { cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Knowledge from '@/features/user/knowledge';
import { mockKbs, mockDocs } from '@/features/knowledge/fixtures';
import { projectKnowledgeDocs } from '@/features/user/catalog/mappers';
import { runtimeStorageKey } from '@/lib/environment';
import type { KnowledgeResource } from '@/features/user/knowledge/schema';

const CHOSEN_STORAGE_KEY = runtimeStorageKey('user.knowledge.chosen');

const fakeApi = vi.hoisted(() => ({
  rows: [] as unknown[],
  request: async (path: string, _init?: unknown) =>
    path.startsWith('/api/catalog/knowledge') ? fakeApi.rows : ({} as unknown),
  get: async (_path: string, _opts?: unknown) => ({} as unknown),
  post: async (_path: string, _body?: unknown) => ({} as unknown),
  delete: async (_path: string) => undefined as unknown,
  upload: async (_path: string, _form?: unknown) => ({} as unknown),
  streamEvents: async function* () {
    // 空流: 对话页不产出任何后端事件.
  },
}));

vi.mock('@qzdap/web-api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@qzdap/web-api')>();
  return { ...actual, getApiClient: () => fakeApi };
});

afterEach(() => cleanup());
beforeEach(() => sessionStorage.removeItem(CHOSEN_STORAGE_KEY));

function renderWithFavorites(resources: KnowledgeResource[]) {
  fakeApi.rows = resources;
  sessionStorage.setItem(CHOSEN_STORAGE_KEY, JSON.stringify([resources[0].id]));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/knowledge']}>
        <Knowledge />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('知识 · 收藏', () => {
  it('restores the persisted favorite state from the server', async () => {
    const resources = projectKnowledgeDocs(mockKbs, mockDocs).map((row, index) =>
      index === 0 ? { ...row, favorited: true } : row,
    );
    renderWithFavorites(resources);

    const button = await screen.findByRole('button', { name: `取消收藏${resources[0].title}` });
    expect(button.getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByText('收藏 1')).toBeTruthy();
  });

  it('does not mark unfavorited resources as collected', async () => {
    const resources = projectKnowledgeDocs(mockKbs, mockDocs);
    renderWithFavorites(resources);

    const button = await screen.findByRole('button', { name: `收藏${resources[0].title}` });
    expect(button.getAttribute('aria-pressed')).toBe('false');
  });
});
