/**
 * SkillDetailPage 测试 — 只读查看，并返回上一级。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

vi.mock('./useAdminSkills', () => ({
  useAdminSkill: vi.fn(),
  useUpdateSkill: () => ({ mutate: vi.fn(), isPending: false }),
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
  tags: ['订单', '摘要'],
  starred: true,
  inputSchema: [],
  outputSchema: [],
  versions: [{ version: 'v1.2.0', publisher: '张敏', releasedAt: '今天', current: true }],
  trend: [10, 20, 30, 40],
  usedByAgents: ['订单客服助手'],
  auditLog: [],
};

function renderAt(id: string) {
  return render(
    <MemoryRouter initialEntries={[`/admin/tools/${id}`]}>
      <Routes>
        <Route path="/admin/tools" element={<div>技能列表</div>} />
        <Route path="/admin/tools/:id" element={<SkillDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('SkillDetailPage', () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    vi.clearAllMocks();
    (useAdminSkill as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: skill,
      isLoading: false,
      isError: false,
    });
  });

  it('renders the skill and a way back', async () => {
    renderAt('skill-summary');
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '订单摘要' })).toBeTruthy();
    });
    expect(screen.getByDisplayValue('生成订单摘要')).toBeTruthy();
    expect(screen.getByText('当前为只读查看。')).toBeTruthy();
    expect(screen.getByRole('button', { name: '编辑' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: '完成' })).toBeNull();
    expect(screen.queryByRole('button', { name: '删除' })).toBeNull();
  });

  it('renders not-found when skill is missing', () => {
    // 技能不存在(接口正常返回空)→ 走 not-found;接口本身报错时页面显示「加载失败」
    (useAdminSkill as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ data: null, isLoading: false, isError: false });
    renderAt('nonexistent');
    expect(screen.getByText(/技能不存在或已被删除/)).toBeTruthy();
  });

  it('shows loading state', () => {
    (useAdminSkill as unknown as ReturnType<typeof vi.fn>).mockReturnValue({ data: null, isLoading: true, isError: false });
    renderAt('skill-summary');
    expect(screen.getByText(/加载中/)).toBeTruthy();
  });
});
