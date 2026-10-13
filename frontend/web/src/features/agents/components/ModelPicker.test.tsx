/**
 * ModelPicker 单测 — mock useModelsList,验证接真数据 + 过滤 + 搜索 + 详情。
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react';
import type { Model } from '@/features/models/schema';

const MODELS: Model[] = [
  {
    id: 'md-gpt4o', name: 'GPT-4o', upstreamModel: 'gpt-4o-2024-08-06',
    providerId: 'pv-openai', providerName: 'OpenAI 官方',
    task: ['reasoning', 'generation'], contextWindow: 128000,
    priceIn: 0.005, priceOut: 0.015, latencyMs: 460, successRate: 99.4,
    status: 'active', tier: 'premium', starred: true, calls: 184320,
    trend: [0], description: 'OpenAI 旗舰多模态,适合复杂推理与高质量生成。',
    tags: ['多模态', '推理'],
  },
  {
    id: 'md-gpt4omini', name: 'GPT-4o mini', upstreamModel: 'gpt-4o-mini',
    providerId: 'pv-openai', providerName: 'OpenAI 官方',
    task: ['generation'], contextWindow: 128000,
    priceIn: 0.00015, priceOut: 0.0006, latencyMs: 280, successRate: 99.6,
    status: 'active', tier: 'economy', starred: false, calls: 286400,
    trend: [0], description: '轻量通用模型。',
    tags: ['轻量'],
  },
  {
    id: 'md-claude35', name: 'Claude 3.5 Sonnet', upstreamModel: 'claude-3-5-sonnet',
    providerId: 'pv-anthropic', providerName: 'Anthropic Claude',
    task: ['reasoning', 'generation', 'summarization'], contextWindow: 200000,
    priceIn: 0.003, priceOut: 0.015, latencyMs: 720, successRate: 98.1,
    status: 'active', tier: 'premium', starred: true, calls: 96400,
    trend: [0], description: '长上下文写作与推理均衡。',
    tags: ['长上下文', '写作'],
  },
  {
    id: 'md-o1preview', name: 'o1-preview', upstreamModel: 'o1-preview',
    providerId: 'pv-openai', providerName: 'OpenAI 官方',
    task: ['reasoning'], contextWindow: 128000,
    priceIn: 0.015, priceOut: 0.06, latencyMs: 1840, successRate: 97.2,
    status: 'graying', tier: 'premium', starred: false, calls: 12480,
    trend: [0], description: '深度推理专用,延迟较高。',
    tags: ['深度推理'],
  },
];

vi.mock('@/features/models/useModels', () => ({
  useModelsList: () => ({ data: MODELS, isLoading: false, error: undefined }),
}));

vi.mock('@/features/models/components/constants', () => ({
  STATUS_BADGE: {
    active: { label: '启用', className: 'bg-emerald-50 text-emerald-700', dot: 'bg-emerald-500' },
    graying: { label: '灰度', className: 'bg-amber-50 text-amber-700', dot: 'bg-amber-500' },
    draft: { label: '草稿', className: 'bg-slate-50 text-slate-700', dot: 'bg-slate-500' },
    retired: { label: '已下线', className: 'bg-rose-50 text-rose-700', dot: 'bg-rose-500' },
  },
}));

// eslint-disable-next-line import/first
import { ModelPicker } from './ModelPicker';

afterEach(() => cleanup());

describe('ModelPicker', () => {
  it('渲染真模型列表(从 useModelsList)', () => {
    render(<ModelPicker selectedId={null} onChange={() => {}} />);
    expect(screen.getByText('GPT-4o')).toBeTruthy();
    expect(screen.getByText('GPT-4o mini')).toBeTruthy();
    expect(screen.getByText('Claude 3.5 Sonnet')).toBeTruthy();
    expect(screen.getByText('o1-preview')).toBeTruthy();
  });

  it('显示提供商标识', () => {
    render(<ModelPicker selectedId={null} onChange={() => {}} />);
    // OpenAI 官方出现 3 次(GPT-4o、GPT-4o mini、o1-preview)
    expect(screen.getAllByText('OpenAI 官方').length).toBe(3);
    expect(screen.getByText('Anthropic Claude')).toBeTruthy();
  });

  it('显示层级 / 状态 / tags', () => {
    render(<ModelPicker selectedId={null} onChange={() => {}} />);
    expect(screen.getAllByText('旗舰').length).toBeGreaterThanOrEqual(2);
    // "经济" 出现在 filter chip 和 GPT-4o mini 的 tier 徽标两处
    expect(screen.getAllByText('经济').length).toBeGreaterThanOrEqual(1);
  });

  it('搜索按名字过滤', () => {
    render(<ModelPicker selectedId={null} onChange={() => {}} />);
    fireEvent.change(screen.getByLabelText('搜索资源'), { target: { value: 'claude' } });
    expect(screen.queryByText('GPT-4o')).toBeNull();
    expect(screen.getByText('Claude 3.5 Sonnet')).toBeTruthy();
  });

  it('搜索按提供商过滤', () => {
    render(<ModelPicker selectedId={null} onChange={() => {}} />);
    fireEvent.change(screen.getByLabelText('搜索资源'), { target: { value: 'anthropic' } });
    expect(screen.getByText('Claude 3.5 Sonnet')).toBeTruthy();
    expect(screen.queryByText('GPT-4o')).toBeNull();
  });

  it('chip 过滤 — 灰度', () => {
    render(<ModelPicker selectedId={null} onChange={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: '灰度' }));
    expect(screen.getByText('o1-preview')).toBeTruthy();
    expect(screen.queryByText('GPT-4o')).toBeNull();
    expect(screen.queryByText('Claude 3.5 Sonnet')).toBeNull();
  });

  it('chip 过滤 — 旗舰 + 启用 组合 AND', () => {
    render(<ModelPicker selectedId={null} onChange={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: '启用' }));
    fireEvent.click(screen.getByRole('button', { name: '旗舰' }));
    // active+premium: GPT-4o + Claude 3.5(都是 active + premium),o1-preview 是 graying 被启用过滤掉
    expect(screen.getByText('GPT-4o')).toBeTruthy();
    expect(screen.getByText('Claude 3.5 Sonnet')).toBeTruthy();
    expect(screen.queryByText('o1-preview')).toBeNull();
    expect(screen.queryByText('GPT-4o mini')).toBeNull();  // economy 被旗舰过滤
  });

  it('allowedStatuses 限制可选 status(graying 时只显示 graying)', () => {
    render(<ModelPicker selectedId={null} onChange={() => {}} allowedStatuses={['graying']} />);
    // 数据流过 allowedStatuses 过滤:graying 数据源只含 o1-preview
    expect(screen.getByText('o1-preview')).toBeTruthy();
    expect(screen.queryByText('GPT-4o')).toBeNull();
  });

  it('点行 → onChange 接收该模型 id', () => {
    const onChange = vi.fn();
    render(<ModelPicker selectedId={null} onChange={onChange} />);
    fireEvent.click(screen.getByText('Claude 3.5 Sonnet'));
    expect(onChange).toHaveBeenLastCalledWith('md-claude35');
  });

  it('selectedId 高亮', () => {
    render(<ModelPicker selectedId="md-gpt4o" onChange={() => {}} />);
    // 列表里 aria-pressed=true 的应是 GPT-4o
    const row = screen.getByText('GPT-4o').closest('[role="button"]') as HTMLElement;
    expect(row.getAttribute('aria-pressed')).toBe('true');
  });

  it('详情预览存在:双击行 → 预览渲染', () => {
    render(<ModelPicker selectedId={null} onChange={() => {}} />);
    expect(screen.queryByText('上下文窗口')).toBeNull();  // 默认空态
    fireEvent.doubleClick(screen.getByText('GPT-4o'));
    expect(screen.getByText('上下文窗口')).toBeTruthy();
    expect(screen.getByText('128k')).toBeTruthy();
    expect(screen.getByText('成功率')).toBeTruthy();
  });

  it('showPreview=false 时无双击预览', () => {
    render(<ModelPicker selectedId={null} onChange={() => {}} showPreview={false} />);
    fireEvent.doubleClick(screen.getByText('GPT-4o'));
    expect(screen.queryByText('上下文窗口')).toBeNull();
  });
});
