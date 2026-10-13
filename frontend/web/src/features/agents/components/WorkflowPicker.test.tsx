/**
 * WorkflowPicker 单测 — mock useWorkflows。
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import type { Flow } from '@/features/workflows/schema';

const FLOWS: Flow[] = [
  {
    id: 'wf-cs', name: '客服工单分流', description: '新工单按关键词路由到不同处理人', owner: '客服部',
    scene: '客服', trigger: '消息触发', status: 'published',
    callCount: 1_200, inputs: 2, outputs: 1,
    createdAt: '2025-01-12', updatedAt: '今天 09:00',
    boundAgents: ['ag-1', 'ag-2'], versions: [{} as Flow['versions'][0]],
    initialNodes: [], initialEdges: [],
  },
  {
    id: 'wf-report', name: '日报推送', description: '每天 9 点向经理推送昨日数据', owner: '运营',
    scene: '运营', trigger: '定时触发', status: 'published',
    callCount: 90, inputs: 0, outputs: 1,
    createdAt: '2024-12-01', updatedAt: '昨天',
    boundAgents: ['ag-3'], versions: [{} as Flow['versions'][0]],
    initialNodes: [], initialEdges: [],
  },
  {
    id: 'wf-billing', name: '计费异常告警', description: '检测到异常推送工单到值班人', owner: '财务',
    scene: '财务', trigger: '事件触发', status: 'draft',
    callCount: 0, inputs: 3, outputs: 1,
    createdAt: '2025-09-01', updatedAt: '3 天前',
    boundAgents: [], versions: [],
    initialNodes: [], initialEdges: [],
  },
];

vi.mock('@/features/workflows/useWorkflows', () => ({
  useWorkflows: () => ({ data: FLOWS, isLoading: false, error: undefined }),
}));

// eslint-disable-next-line import/first
import { WorkflowPicker } from './WorkflowPicker';

afterEach(() => cleanup());

describe('WorkflowPicker', () => {
  it('渲染真工作流列表', () => {
    render(<WorkflowPicker selectedIds={[]} onChange={() => {}} />);
    expect(screen.getByText('客服工单分流')).toBeTruthy();
    expect(screen.getByText('日报推送')).toBeTruthy();
    expect(screen.getByText('计费异常告警')).toBeTruthy();
  });

  it('每项显示触发器 + 状态徽标', () => {
    render(<WorkflowPicker selectedIds={[]} onChange={() => {}} />);
    // "消息触发" 在 1 个数据 + 1 个 chip 中出现
    expect(screen.getAllByText('消息触发').length).toBeGreaterThanOrEqual(2);
    // "定时触发" / "事件触发" 各出现 ≥ 2 次(数据 + chip)
    expect(screen.getAllByText('定时触发').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('事件触发').length).toBeGreaterThanOrEqual(2);
  });

  it('搜索按名字过滤', () => {
    render(<WorkflowPicker selectedIds={[]} onChange={() => {}} />);
    fireEvent.change(screen.getByLabelText('搜索资源'), { target: { value: '日报' } });
    expect(screen.getByText('日报推送')).toBeTruthy();
    expect(screen.queryByText('客服工单分流')).toBeNull();
  });

  it('chip 过滤 — 草稿', () => {
    render(<WorkflowPicker selectedIds={[]} onChange={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: '草稿' }));
    expect(screen.getByText('计费异常告警')).toBeTruthy();
    expect(screen.queryByText('客服工单分流')).toBeNull();
  });

  it('allowedTriggers 限制只能选消息触发', () => {
    render(<WorkflowPicker selectedIds={[]} onChange={() => {}} allowedTriggers={['消息触发']} />);
    expect(screen.getByText('客服工单分流')).toBeTruthy();
    expect(screen.queryByText('日报推送')).toBeNull();
    expect(screen.queryByText('计费异常告警')).toBeNull();
  });

  it('allowedStatuses 限制只能选 published', () => {
    render(<WorkflowPicker selectedIds={[]} onChange={() => {}} allowedStatuses={['published']} />);
    expect(screen.getByText('客服工单分流')).toBeTruthy();
    expect(screen.getByText('日报推送')).toBeTruthy();
    expect(screen.queryByText('计费异常告警')).toBeNull();
  });

  it('multi 模式:点行切换(用受控 wrapper)', () => {
    const onChange = vi.fn();
    const Wrapper = ({ ids }: { ids: string[] }) => (
      <WorkflowPicker selectedIds={ids} onChange={onChange} />
    );
    const { rerender } = render(<Wrapper ids={[]} />);
    fireEvent.click(screen.getByText('客服工单分流'));
    expect(onChange).toHaveBeenLastCalledWith(['wf-cs']);
    rerender(<Wrapper ids={['wf-cs']} />);
    fireEvent.click(screen.getByText('日报推送'));
    expect(onChange).toHaveBeenLastCalledWith(['wf-cs', 'wf-report']);
  });

  it('预览:双击行展示统计', () => {
    render(<WorkflowPicker selectedIds={[]} onChange={() => {}} />);
    fireEvent.doubleClick(screen.getByText('客服工单分流'));
    expect(screen.getByText('调用次数')).toBeTruthy();
    expect(screen.getByText('1,200')).toBeTruthy();
    expect(screen.getByText('2 / 1')).toBeTruthy();  // inputs/outputs
    expect(screen.getByText('2 个')).toBeTruthy();  // bound agents
  });
});
