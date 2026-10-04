import type { ReactNode } from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import MyKnowledge from '@/features/user/knowledge';
import MyAutomations from '@/features/user/automations';
import MyTeam from '@/features/user/team';
import MySkills from '@/features/user/skills';
import { mockAdminSkills } from '@/features/skills/fixtures';
import { mockFlows } from '@/features/workflows/fixtures';
import { mockKbs, mockDocs } from '@/features/knowledge/fixtures';
import { mockTeams, mockMembers, mockSharedItems } from '@/features/user/team/fixtures';
import { projectOpenSkills, projectOpenWorkflows, projectKnowledgeDocs } from '@/features/user/catalog/mappers';
import { qk } from '@/api/shared/query-keys';

const SKILLS_CHOSEN_KEY = 'qzdap.user.skills.chosen';
const AUTOMATIONS_CHOSEN_KEY = 'qzdap.user.automations.chosen';
const KNOWLEDGE_CHOSEN_KEY = 'qzdap.user.knowledge.chosen';

function renderWithProviders(node: ReactNode, chosenSkillIds: string[] = ['skill-summary', 'tool-calendar', 'mcp-drive']) {
  sessionStorage.setItem(SKILLS_CHOSEN_KEY, JSON.stringify(chosenSkillIds));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData([...qk.user.skills.list, {}, 'w1'], projectOpenSkills(mockAdminSkills));
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function wrap(qc: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

afterEach(() => cleanup());
beforeEach(() => {
  sessionStorage.removeItem(SKILLS_CHOSEN_KEY);
  sessionStorage.removeItem(AUTOMATIONS_CHOSEN_KEY);
  sessionStorage.removeItem(KNOWLEDGE_CHOSEN_KEY);
});

describe('我的知识', () => {
  function renderKnowledge(chosen: string[] = ['doc-001', 'doc-006']) {
    sessionStorage.setItem(KNOWLEDGE_CHOSEN_KEY, JSON.stringify(chosen));
    const qc = makeClient();
    qc.setQueryData([...qk.user.knowledge.list, {}, 'w1'], projectKnowledgeDocs(mockKbs, mockDocs));
    return render(<MyKnowledge />, { wrapper: wrap(qc) });
  }

  it('filters resources and opens source details', () => {
    renderKnowledge();
    fireEvent.change(screen.getByPlaceholderText('搜索标题、团队或标签'), { target: { value: '报销' } });
    expect(screen.getAllByText('差旅报销指南.md').length).toBeGreaterThan(0);
    expect(screen.queryByText('产品手册 v3.pdf')).toBeNull();
    fireEvent.click(screen.getByText('差旅报销指南.md'));
    expect(screen.getByRole('dialog', { name: '差旅报销指南.md详情' })).toBeTruthy();
    expect(within(screen.getByRole('dialog', { name: '差旅报销指南.md详情' })).getByText('财务团队')).toBeTruthy();
  });

  it('answers locally and opens a knowledge source', () => {
    renderKnowledge();
    fireEvent.change(screen.getByPlaceholderText('例如：入职第一周要完成什么？'), { target: { value: '产品' } });
    fireEvent.click(screen.getByRole('button', { name: '查看示例' }));
    expect(screen.getByText('示例回答 · 未连接知识服务')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /参考：/ }));
    expect(screen.getByRole('dialog')).toBeTruthy();
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '带入对话' }));
  });

  it('filters by tag and copies a citation', () => {
    renderKnowledge();
    fireEvent.change(screen.getByLabelText('标签'), { target: { value: '产品' } });
    expect(screen.getByText('产品手册 v3.pdf')).toBeTruthy();
    fireEvent.click(screen.getByText('产品手册 v3.pdf'));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '复制引用' }));
    expect(screen.getByRole('status').textContent).toContain('引用摘要已复制');
  });
});

describe('我的工作流', () => {
  function renderAutomations(chosen: string[] = ['wf-weekly', 'wf-complaint']) {
    sessionStorage.setItem(AUTOMATIONS_CHOSEN_KEY, JSON.stringify(chosen));
    const qc = makeClient();
    qc.setQueryData([...qk.user.automations.list, {}, 'w1'], projectOpenWorkflows(mockFlows));
    qc.setQueryData([...qk.user.automations.runs, 'w1'], []);
    return render(<MyAutomations />, { wrapper: wrap(qc) });
  }

  it('filters published flows and records a local use', () => {
    renderAutomations();
    fireEvent.change(screen.getByPlaceholderText('搜索工作流、场景或团队'), { target: { value: '周报' } });
    expect(screen.getByRole('button', { name: '销售周报自动整理' })).toBeTruthy();
    expect(screen.queryByText('新成员入职准备')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /使用工作流/ }));
    expect(screen.getByRole('dialog', { name: '使用销售周报自动整理' })).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText('例如：整理本周华东客户进展'), { target: { value: '本周摘要' } });
    fireEvent.click(screen.getByRole('button', { name: '确认使用' }));
    expect(screen.getByRole('status').textContent).toContain('已加入本地使用记录');
  });

  it('opens steps and favorites a flow', () => {
    renderAutomations();
    fireEvent.click(screen.getAllByRole('button', { name: /查看步骤/ })[0]);
    expect(screen.getByRole('dialog', { name: /工作流详情/ })).toBeTruthy();
    expect(screen.getByText('定时触发')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /关闭工作流详情/ }));
    fireEvent.click(screen.getByRole('button', { name: '收藏销售周报自动整理' }));
    expect(screen.getByRole('button', { name: '取消收藏销售周报自动整理' })).toBeTruthy();
  });
});

describe('我的技能', () => {
  it('switches capability types, favorites, and opens details', () => {
    renderWithProviders(<MySkills />);
    fireEvent.change(screen.getByLabelText('类型'), { target: { value: 'Tool' } });
    expect(screen.getByText('日历安排工具')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '收藏日历安排工具' }));
    expect(screen.getByRole('button', { name: '取消收藏日历安排工具' })).toBeTruthy();
    fireEvent.click(screen.getByRole('heading', { name: '日历安排工具' }));
    expect(screen.getByRole('dialog', { name: '日历安排工具详情' })).toBeTruthy();
  });

  it('confirms a Skill use and records it locally', () => {
    renderWithProviders(<MySkills />);
    fireEvent.click(screen.getByRole('heading', { name: '资料摘要助手' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '使用能力' }));
    expect(screen.getByRole('dialog', { name: '使用资料摘要助手' })).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText('例如：整理本周客户反馈并提取三个行动项'), { target: { value: '整理本周资料' } });
    fireEvent.click(screen.getByRole('button', { name: '确认使用' }));
    expect(screen.getByRole('status').textContent).toContain('已加入本地使用记录');
  });

  it('shows open MCP capabilities from admin skills', () => {
    renderWithProviders(<MySkills />);
    fireEvent.change(screen.getByLabelText('类型'), { target: { value: 'MCP' } });
    fireEvent.click(screen.getByRole('heading', { name: '团队云盘连接' }));
    expect(screen.getByRole('dialog', { name: '团队云盘连接详情' })).toBeTruthy();
    expect(within(screen.getByRole('dialog')).getByRole('button', { name: '使用能力' })).toBeTruthy();
  });
});

describe('我的协作', () => {
  function renderTeam() {
    const qc = makeClient();
    qc.setQueryData([...qk.user.team.root, 'teams', 'w1'], mockTeams);
    qc.setQueryData([...qk.user.team.members, 'w1'], mockMembers);
    qc.setQueryData([...qk.user.team.shared, 'agents', 'w1'], mockSharedItems.filter((item) => item.kind === 'agent'));
    qc.setQueryData([...qk.user.team.shared, 'knowledge', 'w1'], mockSharedItems.filter((item) => item.kind === 'knowledge'));
    return render(<MyTeam />, { wrapper: wrap(qc) });
  }

  it('switches teams and resource tabs, then favorites a shared item', () => {
    renderTeam();
    fireEvent.click(screen.getByRole('tab', { name: '智能体' }));
    expect(screen.getByText('需求梳理伙伴')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '收藏需求梳理伙伴' }));
    expect(screen.getByRole('button', { name: '取消收藏需求梳理伙伴' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /客户成功组/ }));
    expect(screen.getByText('客户沟通助手')).toBeTruthy();
    expect(screen.queryByText('需求梳理伙伴')).toBeNull();
    fireEvent.click(screen.getByText('客户沟通助手'));
    expect(screen.getByRole('dialog', { name: '客户沟通助手详情' })).toBeTruthy();
  });

  it('adds an invitation only to the local demo list', () => {
    renderTeam();
    fireEvent.click(screen.getByRole('button', { name: '邀请成员' }));
    fireEvent.change(screen.getByPlaceholderText('name@company.com'), { target: { value: 'new@company.com' } });
    fireEvent.click(screen.getByRole('button', { name: '加入演示列表' }));
    expect(screen.getByText('new@company.com')).toBeTruthy();
    expect(screen.getByText(/未发送真实邀请/)).toBeTruthy();
  });
});
