/**
 * L3Tab — 团队级知识记忆(卡片网格 + 筛选 + 新建)。
 *
 * 卡片布局:外层 rounded-2xl + 顶部筛选 header(border-b) + 卡片网格 + 底部分页(border-t 内联)。
 * 与 /admin/workflows 列表卡片结构对齐。
 */
import { AdminListPagination } from '@/components/feedback/AdminListPagination';
import { AdminListHeader, AdminListHeaderMetrics } from '@/components/feedback/AdminListRow';
import type { L3Entry, L3Status } from '../../schema';
import { L3_STATUS_BADGE } from '../constants';
import { L3Card } from '../Cards';
import { ListToolbar } from '../ListToolbar';

export function L3Tab({
  entries, teams,
  query, onQuery,
  teamFilter, onTeamFilter,
  statusFilter, onStatusFilter,
  onOpen, onRetire, onPublish,
  onCreate,
  pagination,
}: {
  entries: L3Entry[];
  teams: string[];
  query: string;
  onQuery: (next: string) => void;
  teamFilter: string;
  onTeamFilter: (next: string) => void;
  statusFilter: 'all' | L3Status;
  onStatusFilter: (next: 'all' | L3Status) => void;
  onOpen: (e: L3Entry) => void;
  onRetire: (id: string) => void;
  onPublish: (id: string) => void;
  onCreate: () => void;
  pagination?: { page: number; totalPages: number; total: number; pageStart: number; pageEnd: number; onPageChange: (next: number) => void };
}) {
  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
      <ListToolbar
        search={query}
        onSearch={onQuery}
        searchLabel="搜索知识记忆"
        placeholder="搜索标题 / 摘要 / 类别"
        countLabel={`${pagination?.total ?? entries.length} 条`}
        filters={[
          {
            label: '团队',
            value: teamFilter,
            onChange: onTeamFilter,
            options: [{ value: 'all', label: '全部团队' }, ...teams.map((team) => ({ value: team, label: team }))],
          },
          {
            label: '状态',
            value: statusFilter,
            onChange: (value) => onStatusFilter(value as 'all' | L3Status),
            options: [
              { value: 'all', label: '全部状态' },
              ...(['draft', 'published', 'retired'] as L3Status[]).map((id) => ({ value: id, label: L3_STATUS_BADGE[id].label })),
            ],
          },
        ]}
        action={{ label: '新建知识', onClick: onCreate }}
      />
      <AdminListHeader hasCheckbox={false} hasStar={false} metrics={<AdminListHeaderMetrics labels={['类别', '切片', '更新']} />} />
      <div className="divide-y divide-[var(--border)]">
        {entries.map((k) => (
          <L3Card key={k.id} entry={k} onOpen={() => onOpen(k)} onRetire={() => onRetire(k.id)} onPublish={() => onPublish(k.id)} />
        ))}
        {entries.length === 0 && (
          <p className="p-12 text-center text-xs text-[var(--text-muted)]">
            没有匹配的知识条目,试试调整筛选条件。
          </p>
        )}
      </div>
      {pagination && <AdminListPagination {...pagination} />}
    </section>
  );
}