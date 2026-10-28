/**
 * KbCreatePage 测试 — 路由 /admin/knowledge/kbs/new
 *
 * 验证:返回链接、Hero 标题、左侧 sticky 纵向 stepper、右侧实时预览面板、
 * 底部「下一步/上一步」按钮态、创建按钮存在。
 */
import { describe, expect, it, afterEach } from 'vitest';
import { cleanup, screen } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { qk } from '@/api/shared/query-keys';
import { renderWithProviders, pageQueryKey } from '@/test-utils/seed';
import KbCreatePage from './KbCreatePage';
import { mockSources } from './fixtures';

function renderAt() {
  return renderWithProviders(
    <Routes>
      <Route path="/admin/knowledge/kbs/new" element={<KbCreatePage />} />
    </Routes>,
    {
      initialEntries: ['/admin/knowledge/kbs/new'],
      seeds: [
        { key: pageQueryKey([...qk.admin.knowledge.root, 'sources']), data: mockSources },
      ],
    },
  );
}

describe('AdminKnowledgeKbCreate', () => {
  afterEach(() => cleanup());

  it('renders header, sticky stepper, and read-only live preview', () => {
    renderAt();
    expect(screen.getByRole('heading', { level: 1, name: '新建知识库' })).toBeTruthy();
    expect(screen.getByRole('link', { name: /返回知识管理/ })).toBeTruthy();
    // 「基础信息」既出现在左侧 stepper, 也出现在右侧 workspace header
    expect(screen.getAllByText('基础信息').length).toBeGreaterThan(0);
    // 「数据源」出现在左侧 stepper 第 2 步; 「检索设置」出现在左侧 stepper 第 3 步
    expect(screen.getAllByText('数据源').length).toBeGreaterThan(0);
    expect(screen.getAllByText('检索设置').length).toBeGreaterThan(0);
    expect(screen.getByText('实时预览')).toBeTruthy();
    // step 1 底部应有「下一步」, 不应有「上一步」; 预览面板只读, 不应有「创建知识库」
    expect(screen.getAllByRole('button', { name: /下一步/ }).length).toBeGreaterThan(0);
    expect(screen.queryAllByRole('button', { name: /上一步/ }).length).toBe(0);
    expect(screen.queryByRole('button', { name: /创建知识库/ })).toBeNull();
  });
});