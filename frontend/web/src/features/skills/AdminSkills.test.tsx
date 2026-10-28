/**
 * AdminSkills 测试 — 概览页 + 新建向导 + 卡片操作。
 *
 * 写操作(新建 / 发布 / 删除)一律走后端, 所以这里注入 skills 模块的 mock handler
 * 作为 ApiClient, 页面跑的是真实的 useApiQuery / useApiMutation 链路 ——
 * 列表数据、乐观刷新都来自那个内存 store, 而不是测试里手搓的假状态。
 */
import { describe, expect, it, afterEach, beforeAll } from 'vitest';
import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { Route, Routes, useNavigate } from 'react-router-dom';
import { ApiClient, setApiClient } from '@qzdap/web-api';
import { renderWithProviders } from '@/test-utils/seed';
import AdminSkills from './SkillsPage';
import SkillCreatePage from './SkillCreatePage';
import { wrapMockHandlerWithAdminSkills } from './mock-handler';

const skillsMock = wrapMockHandlerWithAdminSkills(async () => undefined);

beforeAll(() => {
  setApiClient(new ApiClient('', () => null, skillsMock));
});

/**
 * 技能详情页占位。新建成功后页面会跳到 /admin/tools/:id,
 * 这里给一个「返回列表」的出口, 让测试能回到概览页看到新卡片。
 */
function SkillDetailStub() {
  const navigate = useNavigate();
  return (
    <div>
      <span>技能详情页</span>
      <button type="button" onClick={() => navigate('/admin/tools')}>返回技能管理</button>
    </div>
  );
}

/** 新建技能:类型选择器 → 3 步 wizard → 创建 → 回到列表看到新卡片。 */
async function createSkill(name: string) {
  fireEvent.click(screen.getByRole('button', { name: '新建技能' }));
  // /admin/tools/new 不带 type 参数时先选能力类型
  fireEvent.click(screen.getByRole('heading', { level: 3, name: 'Skill' }).closest('button') as HTMLElement);
  fireEvent.change(screen.getByPlaceholderText('例如:客户跟进建议'), { target: { value: name } });
  fireEvent.click(screen.getByRole('button', { name: /下一步/ }));
  fireEvent.click(screen.getByRole('button', { name: /下一步/ }));
  fireEvent.click(screen.getByRole('button', { name: '创建技能' }));
  // 创建成功 → 跳到新技能详情页
  await screen.findByText('技能详情页');
  // 回到概览页, 列表重新拉取后新技能以卡片出现
  fireEvent.click(screen.getByRole('button', { name: '返回技能管理' }));
  expect(await screen.findByRole('heading', { name })).toBeTruthy();
}

function renderPage() {
  return renderWithProviders(
    <Routes>
      <Route path="/admin/tools" element={<AdminSkills />} />
      <Route path="/admin/tools/new" element={<SkillCreatePage />} />
      <Route path="/admin/tools/:id" element={<SkillDetailStub />} />
    </Routes>,
    { initialEntries: ['/admin/tools'] },
  );
}

describe('AdminSkills', () => {
  afterEach(() => cleanup());

  it('renders the overview with a type filter and no type tabs', () => {
    renderPage();
    expect(screen.getByText('维护智能体可调用的技能。')).toBeTruthy();
    expect(screen.queryByRole('navigation', { name: '子模块导航' })).toBeNull();
    expect(screen.getByRole('combobox', { name: '类型' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '新建技能' })).toBeTruthy();
  });

  it('walks through the create page and returns a new card', async () => {
    renderPage();
    await createSkill('测试技能');
    expect(screen.getByRole('button', { name: '新建技能' })).toBeTruthy();
  });

  it('publishes a draft from its card', async () => {
    renderPage();
    await createSkill('待发布技能');
    const card = screen.getByRole('heading', { name: '待发布技能' }).closest('article') as HTMLElement;
    fireEvent.click(within(card).getByRole('button', { name: '发布' }));
    expect(await screen.findByText(/已发布「待发布技能」/)).toBeTruthy();
    // 列表重新拉取后卡片状态变成已发布
    await waitFor(() => {
      const published = screen.getByRole('heading', { name: '待发布技能' }).closest('article') as HTMLElement;
      expect(within(published).getByRole('button', { name: '已发布' })).toBeTruthy();
    });
  });

  it('opens delete confirm modal and cancels', async () => {
    renderPage();
    await createSkill('待删除技能');
    const card = screen.getByRole('heading', { name: '待删除技能' }).closest('article') as HTMLElement;
    fireEvent.click(within(card).getByRole('button', { name: '删除' }));
    const dialog = screen.getByRole('dialog', { name: /删除技能/ });
    expect(dialog).toBeTruthy();
    fireEvent.click(within(dialog).getByRole('button', { name: '取消' }));
    expect(screen.queryByRole('dialog', { name: /删除技能:/ })).toBeNull();
  });

  it('keeps export off the filter bar and opens it from a card selection', async () => {
    renderPage();
    const actions = screen.getByRole('group', { name: '列表操作' });
    expect(within(actions).queryByRole('button', { name: '导出' })).toBeNull();
    expect(screen.queryByRole('combobox', { name: '排序' })).toBeNull();
    await createSkill('待导出技能');
    const card = screen.getByRole('heading', { name: '待导出技能' }).closest('article') as HTMLElement;
    fireEvent.click(within(card).getByRole('button', { name: /选择/ }));
    fireEvent.click(screen.getByRole('button', { name: /批量导出/ }));
    const dialog = screen.getByRole('dialog', { name: '导出技能' });
    expect(dialog).toBeTruthy();
    fireEvent.click(within(dialog).getByRole('button', { name: /下一步/ }));
    const jsonBtn = within(dialog).getByRole('button', { name: /^JSON/ });
    fireEvent.click(jsonBtn);
    fireEvent.click(within(dialog).getByRole('button', { name: '关闭对话框' }));
    expect(screen.queryByRole('dialog', { name: '导出技能' })).toBeNull();
  });

  it('opens the skill page when an overview card is clicked', async () => {
    renderPage();
    await createSkill('可进入技能');
    fireEvent.click(screen.getByRole('button', { name: '查看 可进入技能 详情' }));
    expect(screen.getByText('技能详情页')).toBeTruthy();
  });

  it('opens the detail page in editing mode from a card', async () => {
    renderPage();
    await createSkill('待编辑技能');
    const card = screen.getByRole('heading', { name: '待编辑技能' }).closest('article') as HTMLElement;
    fireEvent.click(within(card).getByRole('button', { name: '编辑' }));
    expect(screen.getByText('技能详情页')).toBeTruthy();
  });
});
