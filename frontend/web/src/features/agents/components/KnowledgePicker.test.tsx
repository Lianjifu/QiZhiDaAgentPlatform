/**
 * KnowledgePicker 单测 — mock useKnowledgeBases。
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import type { Kb } from '@/features/knowledge/schema';

const KBS: Kb[] = [
  {
    id: 'kb-product', name: '产品手册 v3', description: '所有产品线使用说明', owner: '产品部',
    scope: '部门', status: 'indexed', docCount: 128, vectorCount: 4_200,
    updatedAt: '今天 10:24', tags: ['产品', '手册'], tone: 'brand',
    evalHitRate: 92,
  },
  {
    id: 'kb-faq', name: '客户 FAQ', description: '常见问题与解答', owner: '客服',
    scope: '公开', status: 'indexed', docCount: 56, vectorCount: 1_800,
    updatedAt: '昨天', tags: ['客户'], tone: 'success',
    evalHitRate: 88,
  },
  {
    id: 'kb-finance', name: '财务制度', description: '差旅报销流程', owner: '财务',
    scope: '部门', status: 'indexing', docCount: 0, vectorCount: 0,
    updatedAt: '2 小时前', tags: ['财务'], tone: 'warn',
    evalHitRate: 0,
  },
  {
    id: 'kb-old', name: '归档资料', description: '历史归档', owner: '运维',
    scope: '部门', status: 'paused', docCount: 12, vectorCount: 0,
    updatedAt: '3 周前', tags: ['归档'], tone: 'info',
    evalHitRate: 0,
  },
];

vi.mock('@/features/knowledge/useKnowledge', () => ({
  useKnowledgeBases: () => ({ data: KBS, isLoading: false, error: undefined }),
}));

// eslint-disable-next-line import/first
import { KnowledgePicker } from './KnowledgePicker';

afterEach(() => cleanup());

describe('KnowledgePicker', () => {
  it('渲染真知识库列表', () => {
    render(<KnowledgePicker selectedIds={[]} onChange={() => {}} />);
    expect(screen.getByText('产品手册 v3')).toBeTruthy();
    expect(screen.getByText('客户 FAQ')).toBeTruthy();
    expect(screen.getByText('财务制度')).toBeTruthy();
    expect(screen.getByText('归档资料')).toBeTruthy();
  });

  it('每项显示状态徽标', () => {
    render(<KnowledgePicker selectedIds={[]} onChange={() => {}} />);
    // "已索引" 在 2 个 indexed 数据项 + 1 个 chip 中出现
    expect(screen.getAllByText('已索引').length).toBeGreaterThanOrEqual(3);
    // "索引中" 出现 1 次(数据) + 1 次(chip)
    expect(screen.getAllByText('索引中').length).toBeGreaterThanOrEqual(2);
  });

  it('搜索按描述过滤', () => {
    render(<KnowledgePicker selectedIds={[]} onChange={() => {}} />);
    fireEvent.change(screen.getByLabelText('搜索资源'), { target: { value: '归档' } });
    expect(screen.getByText('归档资料')).toBeTruthy();
    expect(screen.queryByText('产品手册 v3')).toBeNull();
  });

  it('chip 过滤 — 已暂停', () => {
    render(<KnowledgePicker selectedIds={[]} onChange={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: '已暂停' }));
    expect(screen.getByText('归档资料')).toBeTruthy();
    expect(screen.queryByText('产品手册 v3')).toBeNull();
  });

  it('allowedStatuses 限制只能选 indexed', () => {
    render(<KnowledgePicker selectedIds={[]} onChange={() => {}} allowedStatuses={['indexed']} />);
    // 3 个 indexed,索引中 / 暂停都被过滤
    expect(screen.getByText('产品手册 v3')).toBeTruthy();
    expect(screen.getByText('客户 FAQ')).toBeTruthy();
    expect(screen.queryByText('财务制度')).toBeNull();
    expect(screen.queryByText('归档资料')).toBeNull();
  });

  it('multi 模式:点行切换(用受控 wrapper)', () => {
    const onChange = vi.fn();
    const Wrapper = ({ ids }: { ids: string[] }) => (
      <KnowledgePicker selectedIds={ids} onChange={onChange} />
    );
    const { rerender } = render(<Wrapper ids={[]} />);
    fireEvent.click(screen.getByText('产品手册 v3'));
    expect(onChange).toHaveBeenLastCalledWith(['kb-product']);
    rerender(<Wrapper ids={['kb-product']} />);
    fireEvent.click(screen.getByText('客户 FAQ'));
    expect(onChange).toHaveBeenLastCalledWith(['kb-product', 'kb-faq']);
  });

  it('预览:双击行展示统计', () => {
    render(<KnowledgePicker selectedIds={[]} onChange={() => {}} />);
    fireEvent.doubleClick(screen.getByText('产品手册 v3'));
    expect(screen.getByText('文档数')).toBeTruthy();
    expect(screen.getByText('128')).toBeTruthy();
    expect(screen.getByText('4,200')).toBeTruthy();
    expect(screen.getByText('92%')).toBeTruthy();
  });
});
