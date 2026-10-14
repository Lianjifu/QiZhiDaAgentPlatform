/**
 * SkillPicker 单测 — mock useAdminSkills 验证类型过滤 + 风险筛选 + 多选。
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import type { Skill } from '@/features/skills/schema';

const SKILLS: Skill[] = [
  {
    id: 'sk-doc', name: '文档摘要', description: '提炼长文档重点', type: 'Skill', versions: [], trend: [], usedByAgents: [], auditLog: [], owner: '知识',
    status: 'published', version: 'v1.0', lastUpdate: '今天',
    calls: 0, successRate: 0, errorRate: 0, avgLatencyMs: 0, rating: 0,
    risk: 'low', needConfirm: false, visibleScope: ['部门'],
    tags: ['整理', '写作'], starred: false, inputSchema: [], outputSchema: [],
  },
  {
    id: 'sk-mailer', name: '邮件发送', description: '在授权邮箱内发送邮件', type: 'Tool', versions: [], trend: [], usedByAgents: [], auditLog: [], owner: '平台工具',
    status: 'published', version: 'v1.0', lastUpdate: '今天',
    calls: 0, successRate: 0, errorRate: 0, avgLatencyMs: 0, rating: 0,
    risk: 'high', needConfirm: true, visibleScope: ['部门'],
    tags: ['邮件'], starred: false, inputSchema: [], outputSchema: [],
  },
  {
    id: 'sk-github', name: 'GitHub MCP', description: '查询仓库、Issue 与 PR', type: 'MCP', versions: [], trend: [], usedByAgents: [], auditLog: [], owner: '平台连接',
    status: 'published', version: 'v1.0', lastUpdate: '今天',
    calls: 0, successRate: 0, errorRate: 0, avgLatencyMs: 0, rating: 0,
    risk: 'medium', needConfirm: true, visibleScope: ['部门'],
    tags: ['代码'], starred: false,
    inputSchema: [{ name: 'repo', type: 'string', required: true, description: '仓库' }],
    outputSchema: [{ name: 'issues', type: 'array', required: true, description: 'Issue 列表' }],
  },
];

vi.mock('@/features/skills/useAdminSkills', () => ({
  useAdminSkills: () => ({ data: SKILLS, isLoading: false, error: undefined }),
}));

vi.mock('@/features/skills/components/constants', () => ({
  TYPE_META: {
    Skill: { icon: () => null, tone: 'bg-violet-50', label: '技能', subLabel: 'Skill', description: '' },
    Tool: { icon: () => null, tone: 'bg-amber-50', label: '技能', subLabel: 'Tool', description: '' },
    MCP: { icon: () => null, tone: 'bg-sky-50', label: '技能', subLabel: 'MCP', description: '' },
  },
  RISK_BADGE: {
    low:    { label: '低风险', className: 'bg-emerald-50', icon: () => null },
    medium: { label: '中等风险', className: 'bg-amber-50', icon: () => null },
    high:   { label: '高风险', className: 'bg-rose-50', icon: () => null },
  },
}));

// eslint-disable-next-line import/first
import { SkillPicker } from './SkillPicker';

afterEach(() => cleanup());

describe('SkillPicker', () => {
  it('渲染真技能列表(从 useAdminSkills)', () => {
    render(<SkillPicker selectedIds={[]} onChange={() => {}} />);
    expect(screen.getByText('文档摘要')).toBeTruthy();
    expect(screen.getByText('邮件发送')).toBeTruthy();
    expect(screen.getByText('GitHub MCP')).toBeTruthy();
  });

  it('每项显示 type 徽标', () => {
    render(<SkillPicker selectedIds={[]} onChange={() => {}} />);
    // 三个 type 文本各出现 ≥ 2 次(filter chip + 徽标)
    expect(screen.getAllByText('Skill').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('Tool').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('MCP').length).toBeGreaterThanOrEqual(2);
  });

  it('高风险显示风险徽标', () => {
    render(<SkillPicker selectedIds={[]} onChange={() => {}} />);
    // 邮件发送 = high, GitHub MCP = medium, 文档摘要 = low(不显)
    // 高徽标 + 中徽标出现
    expect(screen.getByText('高风险')).toBeTruthy();
    expect(screen.getByText('中等风险')).toBeTruthy();
  });

  it('搜索按名字过滤', () => {
    render(<SkillPicker selectedIds={[]} onChange={() => {}} />);
    fireEvent.change(screen.getByLabelText('搜索资源'), { target: { value: 'github' } });
    expect(screen.getByText('GitHub MCP')).toBeTruthy();
    expect(screen.queryByText('邮件发送')).toBeNull();
  });

  it('chip 过滤 — Tool 类型', () => {
    render(<SkillPicker selectedIds={[]} onChange={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: 'Tool' }));
    expect(screen.getByText('邮件发送')).toBeTruthy();
    expect(screen.queryByText('文档摘要')).toBeNull();
    expect(screen.queryByText('GitHub MCP')).toBeNull();
  });

  it('chip 过滤 — MCP + 中等风险 组合', () => {
    render(<SkillPicker selectedIds={[]} onChange={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: 'MCP' }));
    fireEvent.click(screen.getByRole('button', { name: '中等风险' }));
    expect(screen.getByText('GitHub MCP')).toBeTruthy();
    expect(screen.queryByText('邮件发送')).toBeNull();
  });

  it('allowedTypes 限制只能选 Skill + Tool(排除 MCP)', () => {
    render(<SkillPicker selectedIds={[]} onChange={() => {}} allowedTypes={['Skill', 'Tool']} />);
    expect(screen.getByText('文档摘要')).toBeTruthy();
    expect(screen.getByText('邮件发送')).toBeTruthy();
    // MCP 不在列表里
    expect(screen.queryByText('GitHub MCP')).toBeNull();
  });

  it('multi 模式:点行切换(用受控 wrapper 模拟 parent re-render)', () => {
    const onChange = vi.fn();
    const Wrapper = ({ ids }: { ids: string[] }) => (
      <SkillPicker selectedIds={ids} onChange={onChange} />
    );
    const { rerender } = render(<Wrapper ids={[]} />);
    fireEvent.click(screen.getByText('文档摘要'));
    expect(onChange).toHaveBeenLastCalledWith(['sk-doc']);
    rerender(<Wrapper ids={['sk-doc']} />);
    fireEvent.click(screen.getByText('GitHub MCP'));
    expect(onChange).toHaveBeenLastCalledWith(['sk-doc', 'sk-github']);
  });

  it('已选项置顶 + 显示 "已选 N 项"', () => {
    render(<SkillPicker selectedIds={['sk-doc', 'sk-mailer']} onChange={() => {}} />);
    expect(screen.getByText(/已选\s*2\s*项/)).toBeTruthy();
  });

  it('预览:双击行展示 input/output schema', () => {
    render(<SkillPicker selectedIds={[]} onChange={() => {}} />);
    fireEvent.doubleClick(screen.getByText('GitHub MCP'));
    // 字段名 + 类型以不同元素渲染,用正则匹配
    expect(screen.getByText('repo')).toBeTruthy();
    expect(screen.getByText(/string/)).toBeTruthy();
    // 输出字段描述 "Issue 列表" 存在(用正则避免文本打断)
    expect(screen.getByText(/Issue 列表/)).toBeTruthy();
  });

  it('showPreview=false 时无双击预览', () => {
    render(<SkillPicker selectedIds={[]} onChange={() => {}} showPreview={false} />);
    fireEvent.doubleClick(screen.getByText('GitHub MCP'));
    expect(screen.queryByText('repo:string')).toBeNull();
  });
});
