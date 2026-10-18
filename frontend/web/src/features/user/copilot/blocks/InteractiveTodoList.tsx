/**
 * InteractiveTodoList — 右侧 todo 抽屉.
 *
 * 显示当前 LLM 通过 todo_write stub tool 推送的任务列表. LWW — 最后一次
 * todo_write 覆盖前面的内容. 用户不直接操作 (TODO 状态由 LLM 更新),
 * 只是看到当前进度.
 */
import { Check, Circle, Loader2 } from 'lucide-react';
import type { TodoItem } from '../interactiveStore';

const STATUS_ICON = {
  pending: Circle,
  in_progress: Loader2,
  completed: Check,
} as const;

const STATUS_TONE = {
  pending: 'text-[var(--text-muted)]',
  in_progress: 'text-[var(--brand)]',
  completed: 'text-emerald-600 line-through opacity-60',
} as const;

export function InteractiveTodoList({ todos }: { todos: TodoItem[] }) {
  if (todos.length === 0) return null;

  const completed = todos.filter((t) => t.status === 'completed').length;
  const total = todos.length;
  const inProgress = todos.find((t) => t.status === 'in_progress');

  return (
    <aside
      aria-label="任务进度"
      className="hidden w-60 shrink-0 border-l border-[var(--border)] bg-[var(--surface-1)] xl:flex xl:flex-col"
    >
      <header className="border-b border-[var(--border)] px-4 py-3">
        <div className="flex items-baseline justify-between">
          <h2 className="text-xs font-semibold text-[var(--text-secondary)]">
            任务进度
          </h2>
          <span className="tabular-nums text-[10px] text-[var(--text-muted)]">
            {completed} / {total}
          </span>
        </div>
        {inProgress && (
          <p className="mt-1 truncate text-[10px] text-[var(--brand)]">
            {inProgress.active_form ?? inProgress.content}
          </p>
        )}
      </header>
      <ol className="flex-1 space-y-1 overflow-y-auto p-3">
        {todos.map((t, i) => {
          const Icon = STATUS_ICON[t.status];
          const tone = STATUS_TONE[t.status];
          return (
            <li
              key={t.id || i}
              className={`flex items-start gap-2 rounded-md px-2 py-1.5 text-[11px] leading-5 ${tone}`}
            >
              <Icon
                className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${
                  t.status === 'in_progress' ? 'animate-spin' : ''
                }`}
              />
              <span className="min-w-0 flex-1">{t.content}</span>
            </li>
          );
        })}
      </ol>
    </aside>
  );
}