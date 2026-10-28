/**
 * AdminKnowledge 列表页测试 — Hero / 知识库·数据源两个入口 / 卡片 / 批量工具栏 / 跳转导航。
 *
 * 文档与任务在知识库详情查看;评测走侧栏评测中心。本页只验证列表行为 + 点击触发导航。
 */
import { describe, expect, it, afterEach } from 'vitest';
import { cleanup, fireEvent, screen } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { qk } from '@/api/shared/query-keys';
import { renderWithProviders, pageQueryKey } from '@/test-utils/seed';
import KnowledgePage from './KnowledgePage';
import KbDetailPage from './KbDetailPage';
import SourceDetailPage from './SourceDetailPage';
import KbCreatePage from './KbCreatePage';
import SourceCreatePage from './SourceCreatePage';
import { mockKbs, mockDocs, mockSources, mockTasks, mockEvalCases } from './fixtures';

function renderPage() {
  return renderWithProviders(<KnowledgePage />, {
    initialEntries: ['/admin/knowledge'],
    seeds: [
      { key: pageQueryKey([...qk.admin.knowledge.root, 'kbs']), data: mockKbs },
      { key: pageQueryKey([...qk.admin.knowledge.root, 'sources']), data: mockSources },
    ],
  });
}

function renderApp(initialPath: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/admin/knowledge" element={<KnowledgePage />} />
      <Route path="/admin/knowledge/kbs/new" element={<KbCreatePage />} />
      <Route path="/admin/knowledge/kbs/:id" element={<KbDetailPage />} />
      <Route path="/admin/knowledge/sources/new" element={<SourceCreatePage />} />
      <Route path="/admin/knowledge/sources/:id" element={<SourceDetailPage />} />
    </Routes>,
    {
      initialEntries: [initialPath],
      seeds: [
        { key: pageQueryKey([...qk.admin.knowledge.root, 'kbs']), data: mockKbs },
        { key: pageQueryKey([...qk.admin.knowledge.root, 'docs']), data: mockDocs },
        { key: pageQueryKey([...qk.admin.knowledge.root, 'sources']), data: mockSources },
        { key: pageQueryKey([...qk.admin.knowledge.root, 'tasks']), data: mockTasks },
        { key: pageQueryKey([...qk.admin.knowledge.root, 'eval']), data: mockEvalCases },
        { key: pageQueryKey([...qk.admin.knowledge.root, 'kb', 'kb-prod']), data: mockKbs[0] },
        { key: pageQueryKey([...qk.admin.knowledge.root, 'kb', 'kb-hr']), data: mockKbs[1] },
      ],
    },
  );
}

describe('AdminKnowledge', () => {
  afterEach(() => cleanup());

  it('renders hero and two sub-tabs', () => {
    renderPage();
    expect(screen.getByText('把企业知识资产管起来。')).toBeTruthy();
    const tabs = ['知识库', '数据源接入'];
    for (const t of tabs) {
      expect(screen.getAllByText(t).length).toBeGreaterThan(0);
    }
    expect(screen.queryByRole('button', { name: /文档目录/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /任务队列/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /评测中心/ })).toBeNull();
  });

  it('lists kb cards on the default tab', () => {
    renderPage();
    expect(screen.getByText('产品手册 v3')).toBeTruthy();
    expect(screen.getByText('员工手册')).toBeTruthy();
  });

  it('switches to sources tab and lists fixtures', () => {
    renderPage();
    const tabs = screen.getAllByRole('button', { name: /数据源/ });
    fireEvent.click(tabs[0]);
    expect(screen.getByText('产品 Wiki')).toBeTruthy();
    expect(screen.getByText('官网帮助中心')).toBeTruthy();
  });

  it('navigates to kb detail page when clicking a card', () => {
    renderApp('/admin/knowledge');
    fireEvent.click(screen.getByRole('button', { name: /查看 产品手册 v3 详情/ }));
    expect(screen.getByRole('heading', { level: 1, name: '产品手册 v3' })).toBeTruthy();
    expect(screen.getByRole('button', { name: /重建索引/ })).toBeTruthy();
    expect(screen.queryByRole('link', { name: /返回知识管理/ })).toBeNull();
  });

  it('navigates to create kb page (3 steps)', () => {
    renderApp('/admin/knowledge');
    fireEvent.click(screen.getAllByRole('button', { name: /新建知识库/ })[0]);
    expect(screen.getByRole('link', { name: /返回知识管理/ })).toBeTruthy();
    expect(screen.getByRole('heading', { level: 1, name: '新建知识库' })).toBeTruthy();
    expect(screen.getAllByText('基础信息').length).toBeGreaterThan(0);
  });

  it('navigates to create source page', () => {
    renderApp('/admin/knowledge');
    fireEvent.click(screen.getAllByRole('button', { name: /数据源/ })[0]);
    fireEvent.click(screen.getByRole('button', { name: /新增数据源/ }));
    expect(screen.getByRole('heading', { level: 1, name: '新增数据源' })).toBeTruthy();
  });

  it('navigates to source detail page when clicking a card', () => {
    renderApp('/admin/knowledge');
    fireEvent.click(screen.getAllByRole('button', { name: /数据源/ })[0]);
    fireEvent.click(screen.getByRole('button', { name: /查看 产品 Wiki 详情/ }));
    expect(screen.getByRole('heading', { level: 1, name: '产品 Wiki' })).toBeTruthy();
    expect(screen.getByRole('button', { name: /立即同步/ })).toBeTruthy();
    expect(screen.queryByRole('link', { name: /返回知识管理/ })).toBeNull();
  });

  it('shows pagination bar when kb fixture count exceeds page size', () => {
    renderPage();
    const nav = screen.getByRole('navigation', { name: '分页' });
    expect(nav.textContent).toMatch(/1-10/);
    expect(nav.textContent).toMatch(/共\s*12/);
    expect(screen.getAllByRole('button', { name: /第 2 页/ }).length).toBeGreaterThan(0);
  });

  it('switching page on kb tab reveals later kbs', () => {
    renderPage();
    expect(screen.getByText('产品手册 v3')).toBeTruthy();
    fireEvent.click(screen.getAllByRole('button', { name: /第 2 页/ })[0]);
    const nav = screen.getByRole('navigation', { name: '分页' });
    expect(nav.textContent).toMatch(/11-12/);
    expect(screen.getByText('回复话术模板')).toBeTruthy();
  });
});
