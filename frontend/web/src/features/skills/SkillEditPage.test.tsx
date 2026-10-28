/**
 * 技能编辑态 — 详情页 `?edit=1` / 旧 `/edit` 路由。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const updateMutate = vi.fn();

vi.mock('./useAdminSkills', () => ({
  useAdminSkill: vi.fn(),
  useUpdateSkill: () => ({ mutate: updateMutate, isPending: false }),
}));

import { useAdminSkill } from './useAdminSkills';
import SkillDetailPage from './SkillDetailPage';

const skill = {
  id: 'skill-summary',
  name: '订单摘要',
  description: '生成订单摘要',
  type: 'Skill' as const,
  owner: '产品团队',
  status: 'published' as const,
  version: 'v1.2.0',
  lastUpdate: '今天 15:30',
  calls: 12340,
  successRate: 0.97,
  errorRate: 0.03,
  avgLatencyMs: 412,
  rating: 4.7,
  risk: 'low' as const,
  needConfirm: false,
  visibleScope: ['公开' as const],
  tags: ['订单'],
  starred: true,
  inputSchema: [],
  outputSchema: [],
  versions: [],
  trend: [10, 20],
  usedByAgents: [],
  auditLog: [],
};

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/admin/tools" element={<div>技能列表</div>} />
        <Route path="/admin/tools/:id/edit" element={<SkillDetailPage />} />
        <Route path="/admin/tools/:id" element={<SkillDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('SkillDetailPage editing', () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    vi.clearAllMocks();
    (useAdminSkill as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: skill,
      isLoading: false,
      isError: false,
    });
  });

  it('opens editing from ?edit=1', async () => {
    renderAt('/admin/tools/skill-summary?edit=1');
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '订单摘要' })).toBeTruthy();
    });
    expect(screen.getByRole('button', { name: '完成' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /保存修改/ })).toBeNull();
  });

  it('redirects /edit to the detail editing state', async () => {
    renderAt('/admin/tools/skill-summary/edit');
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '完成' })).toBeTruthy();
    });
  });

  it('saves on 完成 when there are changes', async () => {
    renderAt('/admin/tools/skill-summary?edit=1');
    const name = await screen.findByDisplayValue('订单摘要');
    fireEvent.change(name, { target: { value: '订单摘要改' } });
    fireEvent.click(screen.getByRole('button', { name: '完成' }));
    expect(updateMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 'skill-summary',
        patch: expect.objectContaining({ name: '订单摘要改' }),
      }),
      expect.any(Object),
    );
  });

  it('renders not-found when skill is missing', () => {
    // 技能不存在(接口正常返回空)→ 走 not-found;接口本身报错时页面显示「加载失败」
    (useAdminSkill as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ data: null, isLoading: false, isError: false });
    renderAt('/admin/tools/missing?edit=1');
    expect(screen.getByText(/技能不存在或已被删除/)).toBeTruthy();
  });
});
