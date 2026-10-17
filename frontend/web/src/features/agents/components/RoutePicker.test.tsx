/**
 * Phase 22: RoutePicker 单测 — mock useRouteOptions, 验证:
 *   - 真实列表渲染 (route.name + strategy 标签 + fallback 计数)
 *   - enabledOnly 过滤 (默认)
 *   - strategyFilter 限制
 *   - 搜索按 name/task/description
 *   - chip 过滤 (按 strategy)
 *   - 点行 → onChange 接收 route.id
 *   - 详情预览: 选中后显示 strategy 说明 + fallback 链 (含 weight)
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import type { RouteOption } from '../useAgentFactory';

const ROUTES: RouteOption[] = [
  {
    id: 'rt-quality-1', name: '主力质量链', strategy: 'quality-first',
    primary_model_id: 'md-gpt4o',
    fallback_model_ids: ['md-claude35', 'md-gpt4omini'],
    task: 'reasoning', description: '办公对话主力, 失败转移到均衡模型',
    enabled: true,
  },
  {
    id: 'rt-cost-1', name: '低成本兜底', strategy: 'cost-first',
    primary_model_id: 'md-gpt4omini',
    fallback_model_ids: ['md-gpt4o'],
    task: 'generation', description: '低单价优先, 适合大批量生成',
    enabled: true,
  },
  {
    id: 'rt-rr-1', name: '同质轮询', strategy: 'round-robin',
    primary_model_id: 'md-gpt4o',
    fallback_model_ids: ['md-gpt4omini', 'md-claude35'],
    task: 'generation', description: '同质模型分摊流量',
    enabled: true,
  },
  {
    id: 'rt-weighted-1', name: '加权混合', strategy: 'weighted',
    primary_model_id: 'md-gpt4o',
    fallback_model_ids: [
      { id: 'md-claude35', weight: 2.0 },
      { id: 'md-gpt4omini', weight: 0.5 },
    ],
    task: 'generation', description: '按 weight 比例采样',
    enabled: true,
  },
  {
    id: 'rt-disabled', name: '已停用路由', strategy: 'latency-first',
    primary_model_id: 'md-o1preview',
    fallback_model_ids: [],
    task: 'reasoning', description: '因供应商下线停用',
    enabled: false,
  },
];

vi.mock('../useAgentFactory', () => ({
  useRouteOptions: () => ({ data: ROUTES, isLoading: false, error: undefined }),
  ROUTE_STRATEGY_LABEL: {
    'fallback': '失败转移',
    'quality-first': '质量优先',
    'cost-first': '成本优先',
    'latency-first': '延迟优先',
    'round-robin': '轮询',
    'weighted': '加权',
  },
  ROUTE_STRATEGY_DESCRIPTION: {
    'fallback': '按 fallback_model_ids 顺序依次试',
    'quality-first': '按 tier / 成功率 / 延迟选最优',
    'cost-first': '按 (输入价+输出价) 选最便宜',
    'latency-first': '按历史延迟选最快',
    'round-robin': 'fallback 链跨请求轮转, 流量均摊',
    'weighted': '按 weight 比例采样首, 其它按 weight 降序',
  },
}));

// eslint-disable-next-line import/first
import { RoutePicker } from './RoutePicker';

afterEach(() => cleanup());

describe('RoutePicker', () => {
  it('渲染真路由列表(从 useRouteOptions, 默认 enabledOnly 过滤掉 disabled)', () => {
    render(<RoutePicker selectedId={null} onChange={() => {}} />);
    expect(screen.getByText('主力质量链')).toBeTruthy();
    expect(screen.getByText('低成本兜底')).toBeTruthy();
    expect(screen.getByText('同质轮询')).toBeTruthy();
    expect(screen.getByText('加权混合')).toBeTruthy();
    // 默认 enabledOnly=true 过滤掉
    expect(screen.queryByText('已停用路由')).toBeNull();
  });

  it('enabledOnly=false 时显示 disabled 路由', () => {
    render(<RoutePicker selectedId={null} onChange={() => {}} enabledOnly={false} />);
    expect(screen.getByText('已停用路由')).toBeTruthy();
  });

  it('strategyFilter 限制可选项到指定 strategy', () => {
    render(<RoutePicker selectedId={null} onChange={() => {}} strategyFilter="round-robin" />);
    expect(screen.getByText('同质轮询')).toBeTruthy();
    expect(screen.queryByText('主力质量链')).toBeNull();
    expect(screen.queryByText('低成本兜底')).toBeNull();
    expect(screen.queryByText('加权混合')).toBeNull();
  });

  it('strategyFilter 接受数组 (多 strategy)', () => {
    render(
      <RoutePicker
        selectedId={null}
        onChange={() => {}}
        strategyFilter={['round-robin', 'weighted']}
      />,
    );
    expect(screen.getByText('同质轮询')).toBeTruthy();
    expect(screen.getByText('加权混合')).toBeTruthy();
    expect(screen.queryByText('主力质量链')).toBeNull();
  });

  it('显示 strategy 标签', () => {
    render(<RoutePicker selectedId={null} onChange={() => {}} />);
    expect(screen.getAllByText('质量优先').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('成本优先').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('轮询').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('加权').length).toBeGreaterThanOrEqual(1);
  });

  it('显示 fallback 数量', () => {
    render(<RoutePicker selectedId={null} onChange={() => {}} />);
    // 主力质量链有 2 个 fallback
    const rows = screen.getAllByText(/fallback × 2/);
    expect(rows.length).toBeGreaterThanOrEqual(1);
    // 低成本兜底有 1 个
    expect(screen.getByText(/fallback × 1/)).toBeTruthy();
  });

  it('搜索按 name 过滤', () => {
    render(<RoutePicker selectedId={null} onChange={() => {}} />);
    fireEvent.change(screen.getByLabelText('搜索资源'), { target: { value: '加权' } });
    expect(screen.getByText('加权混合')).toBeTruthy();
    expect(screen.queryByText('主力质量链')).toBeNull();
  });

  it('搜索按 task 过滤 (reasoning 原始值)', () => {
    render(<RoutePicker selectedId={null} onChange={() => {}} />);
    fireEvent.change(screen.getByLabelText('搜索资源'), { target: { value: 'reasoning' } });
    // 主力质量链 task=reasoning
    expect(screen.getByText('主力质量链')).toBeTruthy();
    expect(screen.queryByText('低成本兜底')).toBeNull();
  });

  it('chip 过滤 — 轮询', () => {
    render(<RoutePicker selectedId={null} onChange={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: '轮询' }));
    expect(screen.getByText('同质轮询')).toBeTruthy();
    expect(screen.queryByText('主力质量链')).toBeNull();
    expect(screen.queryByText('低成本兜底')).toBeNull();
  });

  it('chip 过滤 — 加权', () => {
    render(<RoutePicker selectedId={null} onChange={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: '加权' }));
    expect(screen.getByText('加权混合')).toBeTruthy();
    expect(screen.queryByText('同质轮询')).toBeNull();
  });

  it('详情预览: 双击行后展示 strategy 说明 + fallback 链 (含 weight)', () => {
    render(<RoutePicker selectedId={null} onChange={() => {}} />);
    fireEvent.doubleClick(screen.getByText('加权混合'));
    // strategy 说明文字至少出现一次 (preview + 列表项)
    expect(screen.getAllByText(/按 weight 比例采样/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Fallback 链/).length).toBeGreaterThanOrEqual(1);
    // fallback dict 显示 weight 标签
    expect(screen.getByText('w=2')).toBeTruthy();
    expect(screen.getByText('w=0.5')).toBeTruthy();
  });

  it('点行 → onChange 接收 route.id', () => {
    const onChange = vi.fn();
    render(<RoutePicker selectedId={null} onChange={onChange} />);
    fireEvent.click(screen.getByText('主力质量链'));
    expect(onChange).toHaveBeenLastCalledWith('rt-quality-1');
  });

  it('selectedId 高亮 (aria-pressed=true)', () => {
    render(<RoutePicker selectedId="rt-quality-1" onChange={() => {}} />);
    const row = screen.getByText('主力质量链').closest('[role="button"]') as HTMLElement;
    expect(row.getAttribute('aria-pressed')).toBe('true');
  });

  it('showPreview=false 时无双击预览', () => {
    render(<RoutePicker selectedId={null} onChange={() => {}} showPreview={false} />);
    // 没 selectedId → 默认就不显示预览
    expect(screen.queryByText('Fallback 链')).toBeNull();
    fireEvent.doubleClick(screen.getByText('主力质量链'));
    expect(screen.queryByText('Fallback 链')).toBeNull();
  });
});
