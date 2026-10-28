/**
 * DocDetailPage 测试 — 路由 /admin/knowledge/docs/:id
 */
import { describe, expect, it, afterEach } from 'vitest';
import { cleanup, screen } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { qk } from '@/api/shared/query-keys';
import { renderWithProviders, pageQueryKey } from '@/test-utils/seed';
import DocDetailPage from './DocDetailPage';
import { mockKbs, mockDocs, mockSources, mockEvalCases } from './fixtures';

function renderAt(id: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/admin/knowledge/docs/:id" element={<DocDetailPage />} />
    </Routes>,
    {
      initialEntries: [`/admin/knowledge/docs/${id}`],
      seeds: [
        { key: pageQueryKey([...qk.admin.knowledge.root, 'kbs']), data: mockKbs },
        { key: pageQueryKey([...qk.admin.knowledge.root, 'docs']), data: mockDocs },
        { key: pageQueryKey([...qk.admin.knowledge.root, 'sources']), data: mockSources },
        { key: pageQueryKey([...qk.admin.knowledge.root, 'eval']), data: mockEvalCases },
      ],
    },
  );
}

describe('AdminKnowledgeDocDetail', () => {
  afterEach(() => cleanup());

  it('renders doc name and stat trio for known id', () => {
    renderAt('doc-001');
    expect(screen.getByRole('heading', { level: 1, name: '产品手册 v3.pdf' })).toBeTruthy();
    expect(screen.getByRole('link', { name: /返回知识管理/ })).toBeTruthy();
    expect(screen.getByText('大小')).toBeTruthy();
    expect(screen.getByText('切片')).toBeTruthy();
    expect(screen.getByText('引用')).toBeTruthy();
    expect(screen.getByText('产品定位')).toBeTruthy();
    expect(screen.getByText('核心功能矩阵')).toBeTruthy();
    expect(screen.getAllByText(/切片预览/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/评测引用/).length).toBeGreaterThan(0);
  });

  it('shows not-found when id is unknown', () => {
    renderAt('doc-does-not-exist');
    expect(screen.getByText('文档不存在或已被删除')).toBeTruthy();
  });
});