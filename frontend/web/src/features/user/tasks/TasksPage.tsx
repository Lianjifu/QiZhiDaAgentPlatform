import { Archive, Check, CheckCircle2, ChevronRight, CircleAlert, CircleDot, Clock3, ListTodo, Play, RotateCcw } from 'lucide-react';
import { useMemo, useState } from 'react';
import { NoticeBanner } from '@/components/feedback/NoticeBanner';
import { SideDrawer } from '@/components/feedback/SideDrawer';
import { CardActionButton, CardActions, CatalogToolbar, EmptyFilterState, PageIntro, WorkspacePage } from '../components';
import { useTasks, useUpdateTask } from './useTasks';
import type { Task, TaskFilter, TaskView, TaskStatus } from './schema';

const STATUS_META: Record<TaskStatus, { icon: typeof CircleDot; className: string; hint: string }> = {
  '待处理': { icon: Clock3, className: 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300', hint: '需要你的确认' },
  '执行中': { icon: Play, className: 'bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300', hint: '正在自动推进' },
  '已完成': { icon: CheckCircle2, className: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300', hint: '最近完成记录' },
  '异常': { icon: CircleAlert, className: 'bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300', hint: '建议尽快处理' },
};
const STATUSES: TaskStatus[] = ['待处理', '执行中', '已完成', '异常'];

function TaskRow({ task, onOpen }: { task: Task; onOpen: (task: Task) => void }) {
  const meta = STATUS_META[task.status];
  const Icon = meta.icon;
  const isHighPriority = task.priority === '高';
  return (
    <button type="button" onClick={() => onOpen(task)} className="group flex w-full items-center gap-4 px-5 py-4 text-left transition hover:bg-[var(--bg-elevated)] sm:px-6">
      <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${meta.className}`}><Icon className="h-4 w-4" /></span>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-2">
          <span className="truncate text-sm font-semibold group-hover:text-[var(--brand)]">{task.title}</span>
          <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${isHighPriority ? 'bg-rose-50 text-rose-600 dark:bg-rose-500/15 dark:text-rose-300' : 'bg-[var(--bg-hover)] text-[var(--text-muted)]'}`}>{task.priority}优先级</span>
        </span>
        <span className="mt-1 block truncate text-xs text-[var(--text-muted)]">{task.source} · {task.owner}</span>
      </span>
      <span className="hidden min-w-[130px] items-center gap-2 text-xs text-[var(--text-muted)] lg:flex"><Clock3 className="h-3.5 w-3.5" />{task.due}</span>
      <span className="hidden w-32 text-xs text-[var(--text-muted)] xl:block">{task.time}</span>
      <ChevronRight className="h-4 w-4 shrink-0 text-[var(--text-muted)]" />
    </button>
  );
}

function TaskScheduleCard({ task, onOpen }: { task: Task; onOpen: (task: Task) => void }) {
  const meta = STATUS_META[task.status];
  return (
    <button type="button" onClick={() => onOpen(task)} className="rounded-xl border border-[var(--border)] p-4 text-left hover:border-[var(--brand)]">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold">{task.due}</span>
        <span className={`rounded-full px-2 py-1 text-[10px] font-semibold ${meta.className}`}>{task.status}</span>
      </div>
      <h4 className="mt-4 text-sm font-semibold">{task.title}</h4>
      <p className="mt-2 line-clamp-2 text-xs leading-5 text-[var(--text-muted)]">{task.description}</p>
      <p className="mt-4 text-[11px] text-[var(--text-muted)]">{task.source} · {task.owner}</p>
    </button>
  );
}

function StatusCard({ status, count, active, onSelect }: { status: TaskStatus; count: number; active: boolean; onSelect: (status: TaskStatus) => void }) {
  const meta = STATUS_META[status];
  const Icon = meta.icon;
  return (
    <button
      type="button"
      onClick={() => onSelect(status)}
      aria-pressed={active}
      className={`rounded-2xl border p-4 text-left transition ${active ? 'border-[var(--brand)] bg-[var(--brand-light)]' : 'border-[var(--border)] bg-[var(--surface-1)] hover:border-[var(--brand)]'}`}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-[var(--text-muted)]">{status}</span>
        <span className={`grid h-8 w-8 place-items-center rounded-lg ${meta.className}`}><Icon className="h-4 w-4" /></span>
      </div>
      <p className="mt-3 text-2xl font-semibold tabular-nums">{count}</p>
      <p className="mt-1 text-[11px] text-[var(--text-muted)]">{meta.hint}</p>
    </button>
  );
}

export default function TasksPage() {
  const tasksQuery = useTasks();
  const tasks = tasksQuery.data ?? [];
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<TaskFilter>('all');
  const [view, setView] = useState<TaskView>('list');
  const [selected, setSelected] = useState<Task | null>(null);
  const [notice, setNotice] = useState('');
  const [sourceFilter, setSourceFilter] = useState('all');
  const updateMutation = useUpdateTask();
  const sources = useMemo(
    () => ['all', ...Array.from(new Set(tasks.map((task) => task.source)))],
    [tasks],
  );

  const filtered = useMemo(() => tasks.filter((task) =>
    (status === 'all' || task.status === status) &&
    (sourceFilter === 'all' || task.source === sourceFilter) &&
    `${task.title} ${task.source} ${task.owner}`.toLowerCase().includes(query.trim().toLowerCase()),
  ), [tasks, status, sourceFilter, query]);

  const counts = useMemo(
    () => STATUSES.reduce((result, item) => ({ ...result, [item]: tasks.filter((task) => task.status === item).length }), {} as Record<TaskStatus, number>),
    [tasks],
  );

  const updateTask = (task: Task, action: 'complete' | 'retry' | 'archive') => {
    if (action === 'archive') {
      updateMutation.mutate({ id: task.id, action }, { onSuccess: () => { setSelected(null); setNotice(`"${task.title}"已归档。`); }, onError: (error) => setNotice(`归档失败：${String(error)}`) });
      return;
    }
    updateMutation.mutate({ id: task.id, action }, { onSuccess: () => { setSelected(null); setNotice(action === 'retry' ? `"${task.title}"已重新运行。` : `"${task.title}"已完成。`); }, onError: (error) => setNotice(`操作失败：${String(error)}`) });
  };

  return (
    <WorkspacePage>
      <PageIntro
        title="任务"
        description="按状态跟进待确认、执行中与异常事项。"
        meta={
          <>
            <span>待处理 {counts['待处理']}</span>
            <span>异常 {counts['异常']}</span>
            <span>共 {tasks.length} 项</span>
          </>
        }
        actions={
          <button
            type="button"
            onClick={() => setNotice('创建任务接口暂未提供。')}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]"
          >
            <ListTodo className="h-3.5 w-3.5" />记录新任务
          </button>
        }
      />
      {notice && <NoticeBanner tone="sky" onClose={() => setNotice('')}>{notice}</NoticeBanner>}
      {tasksQuery.isError && <p role="alert" className="rounded-xl border border-rose-300 bg-rose-50 px-4 py-3 text-sm text-rose-700">加载失败：{String(tasksQuery.error)}</p>}
      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {STATUSES.map((item) => (
          <StatusCard
            key={item}
            status={item}
            count={counts[item]}
            active={status === item}
            onSelect={(next) => setStatus(status === next ? 'all' : next)}
          />
        ))}
      </section>
      <section className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
        <CatalogToolbar
          search={query}
          onSearch={setQuery}
          searchLabel="搜索任务"
          placeholder="搜索任务、来源或负责人"
          filters={[
            {
              label: '任务来源',
              value: sourceFilter,
              onChange: setSourceFilter,
              options: sources.map((source) => ({ value: source, label: source === 'all' ? '全部来源' : source })),
            },
            {
              label: '任务视图',
              value: view,
              onChange: (value) => setView(value as TaskView),
              options: [
                { value: 'list', label: '列表视图' },
                { value: 'schedule', label: '日程视图' },
              ],
            },
          ]}
          countLabel={`${filtered.length} 项`}
          actions={
            status !== 'all' ? (
              <button type="button" onClick={() => setStatus('all')} className="h-9 rounded-lg border border-[var(--border)] px-3 text-xs font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]">
                清除状态
              </button>
            ) : null
          }
        />
        {view === 'list' ? (
          <div className="divide-y divide-[var(--border)]">
            {filtered.map((task) => <TaskRow key={task.id} task={task} onOpen={setSelected} />)}
          </div>
        ) : (
          <div className="grid gap-4 p-5 md:grid-cols-2 xl:grid-cols-3">
            {filtered.map((task) => <TaskScheduleCard key={task.id} task={task} onOpen={setSelected} />)}
          </div>
        )}
        {filtered.length === 0 && (
          <EmptyFilterState title="没有匹配的任务" description="尝试更换状态、来源或关键词。" />
        )}
      </section>
      <SideDrawer
        open={selected !== null}
        onClose={() => setSelected(null)}
        ariaLabel={selected ? `${selected.title}详情` : '任务详情'}
        eyebrow={<p className="text-[11px] font-semibold text-[var(--brand)]">任务详情</p>}
        closeLabel="关闭任务详情"
      >
        {selected && (
          <>
            <h3 className="mt-10 text-2xl font-semibold">{selected.title}</h3>
            <p className="mt-3 text-sm leading-7 text-[var(--text-muted)]">{selected.description}</p>
            <div className="mt-7 grid grid-cols-2 gap-3 text-xs">
              <div className="rounded-xl bg-[var(--bg-elevated)] p-4">
                <p className="text-[var(--text-muted)]">来源</p>
                <p className="mt-2 font-semibold">{selected.source}</p>
              </div>
              <div className="rounded-xl bg-[var(--bg-elevated)] p-4">
                <p className="text-[var(--text-muted)]">截止时间</p>
                <p className="mt-2 font-semibold">{selected.due}</p>
              </div>
            </div>
            <CardActions>
              {selected.status === '待处理' && (
                <CardActionButton tone="brand" onClick={() => updateTask(selected, 'complete')}>
                  <Check className="h-3.5 w-3.5" />确认完成
                </CardActionButton>
              )}
              {selected.status === '异常' && (
                <CardActionButton tone="brand" onClick={() => updateTask(selected, 'retry')}>
                  <RotateCcw className="h-3.5 w-3.5" />重新运行
                </CardActionButton>
              )}
              <CardActionButton tone="danger" onClick={() => updateTask(selected, 'archive')}>
                <Archive className="h-3.5 w-3.5" />归档记录
              </CardActionButton>
            </CardActions>
            <p className="mt-7 text-xs leading-6 text-[var(--text-muted)]">任务数据来自后端 API，操作结果以服务端返回为准。</p>
          </>
        )}
      </SideDrawer>
    </WorkspacePage>
  );
}
