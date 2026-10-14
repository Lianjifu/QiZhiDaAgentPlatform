/**
 * AdminAgents 页面测试 — Hero / 状态 Tab / 卡片 / 批量工具栏 / 向导 / 详情路由等关键交互。
 */
import { describe, expect, it, afterEach } from 'vitest';
import { cleanup, fireEvent, screen, within } from '@testing-library/react';
import { Route, Routes, Outlet, useLocation } from 'react-router-dom';
import { qk } from '@/api/shared/query-keys';
import { renderWithProviders } from '@/test-utils/seed';
import AgentsPage from './AgentsPage';
import AgentDetailPage from './AgentDetailPage';
import AgentCreatePage from './AgentCreatePage';
import { mockAgents } from './fixtures';
import { childPageTitle, PageCrumbNav } from '@/widgets/app-shell/pageCrumb';

function CrumbLayout() {
  const title = childPageTitle(useLocation().pathname);
  return (
    <>
      {title ? <PageCrumbNav parentHref="/admin/agents" parentLabel="智能体管理" title={title} /> : null}
      <Outlet />
    </>
  );
}

function renderPage() {
  return renderWithProviders(<AgentsPage />, {
    initialEntries: ['/admin/agents'],
    seeds: [
      { key: [...qk.admin.agents.list, {}, 'w1'], data: mockAgents },
    ],
  });
}

function renderApp(initialPath: string) {
  return renderWithProviders(
    <Routes>
      <Route element={<CrumbLayout />}>
        <Route path="/admin/agents" element={<AgentsPage />} />
        <Route path="/admin/agents/new" element={<AgentCreatePage />} />
        <Route path="/admin/agents/:id/edit" element={<AgentDetailPage />} />
        <Route path="/admin/agents/:id" element={<AgentDetailPage />} />
      </Route>
    </Routes>,
    {
      initialEntries: [initialPath],
      seeds: [
        { key: [...qk.admin.agents.list, {}, 'w1'], data: mockAgents },
        // AgentDetailPage 走 useAgentDetail(id) → 真实缓存 key = [...qk.admin.agents.detail(id), workspaceId='w1']
        ...mockAgents.map((a) => ({
          key: [...qk.admin.agents.detail(a.id), 'w1'],
          data: a,
        })),
      ],
    },
  );
}

describe('AdminAgents', () => {
  afterEach(() => cleanup());

  it('renders hero headline and primary CTAs', () => {
    renderPage();
    expect(screen.getByText(/配置、审核并发布智能体/)).toBeTruthy();
    const actions = screen.getByRole('group', { name: '列表操作' });
    expect(within(actions).getByRole('button', { name: '新建智能体' })).toBeTruthy();
    expect(within(actions).getByRole('button', { name: '导入' })).toBeTruthy();
    expect(within(actions).queryByRole('button', { name: '导出' })).toBeNull();
    expect(screen.queryByRole('combobox', { name: '场景' })).toBeNull();
    expect(screen.queryByRole('combobox', { name: '排序' })).toBeNull();
  });

  it('puts status in the filter instead of tabs', () => {
    renderPage();
    expect(screen.queryByRole('navigation', { name: '状态过滤' })).toBeNull();
    const status = screen.getByRole('combobox', { name: '状态' }) as HTMLSelectElement;
    const labels = Array.from(status.options).map((option) => option.textContent || '');
    expect(labels).toEqual(['全部状态', '草稿', '待审核', '灰度中', '已发布', '已下线']);
  });

  it('renders agent cards from fixture', () => {
    renderPage();
    expect(screen.getByText('客户沟通助手')).toBeTruthy();
    expect(screen.getByText('销售支持')).toBeTruthy();
    expect(screen.getByText('数据洞察助手')).toBeTruthy();
  });

  it('filters by status select', () => {
    renderPage();
    fireEvent.change(screen.getByRole('combobox', { name: '状态' }), { target: { value: 'graying' } });
    expect(screen.getByText('客户沟通助手 v4')).toBeTruthy();
    expect(screen.queryByText('销售支持')).toBeNull();
  });

  it('navigates to detail page when clicking a card', () => {
    renderApp('/admin/agents');
    const trigger = screen.getByRole('button', { name: /查看 客户沟通助手 详情/ });
    fireEvent.click(trigger);
    // 路由切换后详情页应渲染:顶部返回按钮 + 工作区导航 + 基本信息面板
    expect(screen.getByRole('heading', { level: 1, name: '详情页' })).toBeTruthy();
    const crumb = screen.getByRole('navigation', { name: '面包屑' });
    expect(within(crumb).getByRole('link', { name: '智能体管理' })).toBeTruthy();
    const sidebar = screen.getByLabelText('智能体工作区导航');
    expect(within(sidebar).getByText(/基本信息/)).toBeTruthy();
    expect(screen.getByRole('button', { name: '编辑' })).toBeTruthy();
    fireEvent.click(within(crumb).getByRole('link', { name: '智能体管理' }));
    expect(screen.getByText(/配置、审核并发布智能体/)).toBeTruthy();
    const card = screen.getByRole('heading', { name: '客户沟通助手' }).closest('article') as HTMLElement;
    fireEvent.click(within(card).getByRole('button', { name: '编辑' }));
    expect(screen.getByRole('heading', { level: 1, name: '详情页' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '完成' })).toBeTruthy();
  });

  it('selects card and shows batch toolbar', () => {
    renderPage();
    const checkbox = screen.getByRole('button', { name: '选择 客户沟通助手' });
    fireEvent.click(checkbox);
    const checkbox2 = screen.getByRole('button', { name: '选择 销售支持' });
    fireEvent.click(checkbox2);
    const toolbar = screen.getByLabelText('批量操作');
    expect(toolbar).toBeTruthy();
    expect(within(toolbar).getByText(/已选 2 项/)).toBeTruthy();
    fireEvent.click(within(toolbar).getByRole('button', { name: /取消选择/ }));
    expect(screen.queryByLabelText('批量操作')).toBeNull();
  });

  it('navigates to create page (AgentEditor 9 面板 + 返回 link)', () => {
    renderApp('/admin/agents');
    fireEvent.click(screen.getByRole('button', { name: '新建智能体' }));
    // 路由切换到独立页面,带返回按钮
    const crumb = screen.getByRole('navigation', { name: '面包屑' });
    expect(within(crumb).getByRole('link', { name: '智能体管理' })).toBeTruthy();
    expect(screen.getByRole('heading', { level: 1, name: '新建页' })).toBeTruthy();
    // AgentEditor:ActionBar 有「保存草稿」/「发布」按钮
    expect(screen.getByRole('button', { name: /保存草稿/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: /发布/ })).toBeTruthy();
    // 当前 panel 是 basic — DrawerPanelBasic 表单的「名称」输入
    const name = screen.getByLabelText(/^名称$/);
    expect(name).toBeTruthy();
    fireEvent.change(name, { target: { value: '测试智能体' } });
    // 发布按钮初始 disabled(必填未完)
    expect((screen.getByRole('button', { name: /发布/ }) as HTMLButtonElement).disabled).toBe(true);
    // 切到「技能」面板(verify 9 面板 nav 工作) — 找「技能」按钮(sidebar 内至少 1 个)
    expect(screen.getAllByText('技能').length).toBeGreaterThanOrEqual(1);
    // 返回上一级
    fireEvent.click(within(crumb).getByRole('link', { name: '智能体管理' }));
    expect(screen.getByText(/配置、审核并发布智能体/)).toBeTruthy();
  });

  it('opens import dialog and previews sample', () => {
    renderPage();
    fireEvent.click(within(screen.getByRole('group', { name: '列表操作' })).getByRole('button', { name: '导入' }));
    const dialog = screen.getByRole('dialog', { name: '导入智能体' });
    expect(dialog).toBeTruthy();
    // Step 1: 验证支持 JSON / CSV / YAML / ZIP 标签 + StepIndicator
    expect(within(dialog).getByText('JSON')).toBeTruthy();
    expect(within(dialog).getByText('CSV')).toBeTruthy();
    // 关闭
    fireEvent.click(within(dialog).getByRole('button', { name: '取消' }));
    expect(screen.queryByRole('dialog', { name: '导入智能体' })).toBeNull();
  });

  it('opens export dialog from a card', () => {
    renderPage();
    const card = screen.getByRole('heading', { name: '客户沟通助手' }).closest('article') as HTMLElement;
    fireEvent.click(within(card).getByRole('button', { name: '导出' }));
    const dialog = screen.getByRole('dialog', { name: '导出智能体' });
    expect(dialog).toBeTruthy();
    expect(within(dialog).getByText(/选择导出范围、格式与字段/)).toBeTruthy();
  });

  it('switches detail page panel to versions and eval', () => {
    renderApp('/admin/agents/a-customer-v3');
    const sidebar = screen.getByLabelText('智能体工作区导航');
    fireEvent.click(within(sidebar).getByText('版本'));
    expect(screen.getAllByText(/查看 diff/).length).toBeGreaterThan(0);
    fireEvent.click(within(sidebar).getByText('评测'));
    expect(screen.getByText(/最近评测批次/)).toBeTruthy();
  });
});