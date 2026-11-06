/**
 * 会话列表项 ✓ —— 状态点 + 标题 + 预览 + **相对时间** ✓。
 *
 * ⚠️ **状态点是真的** ✓ —— 「等你确认」来自轮次表 ✓（后端算的 ✓）；
 * 「上次失败」也来自轮次表 ✓ —— 不是猜的 ✓。
 */
import { memo } from 'react';
import { Trash2 } from 'lucide-react';
import type { CopilotSession } from '../schema';
import { formatRelativeTime } from './relativeTime';

export type SessionListItemProps = {
  session: CopilotSession;
  active: boolean;
  onSelect: (session: CopilotSession) => void;
  onDelete: (session: CopilotSession) => void;
};

function statusOf(session: CopilotSession): 'waiting' | 'failed' | 'idle' {
  if (session.waitStatus === 'waiting_approval') return 'waiting';
  if (session.lastStatus === 'failed') return 'failed';
  return 'idle';
}

const DOT_CLASS: Record<'waiting' | 'failed' | 'idle', string> = {
  waiting: 'bg-amber-500',
  failed: 'bg-rose-500',
  idle: 'bg-slate-300',
};

/**
 * 预览里那些 **markdown 记号** 要清掉 ✓ —— 列表里一行字 ✗✗ 谁要看
 * `**结论：**` 这种 ✗✗。
 */
function plainPreview(text: string): string {
  return text
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/[*_`>#|~-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

export const SessionListItem = memo(function SessionListItem({
  session,
  active,
  onSelect,
  onDelete,
}: SessionListItemProps) {
  const status = statusOf(session);
  const relative = formatRelativeTime(session.updatedAt);
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onSelect(session)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onSelect(session);
        }
      }}
      className={`group relative flex w-full cursor-pointer flex-col gap-1 rounded-md px-2.5 py-2 text-left transition ${
        active
          ? 'bg-[var(--brand-light)] text-[var(--brand)]'
          : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]'
      }`}
    >
      <span className="flex items-center gap-1.5">
        <span
          className={`h-1.5 w-1.5 shrink-0 rounded-full ${DOT_CLASS[status]}`}
          aria-hidden="true"
        />
        <span className="truncate text-xs font-semibold">{session.title}</span>
      </span>
      <span className="flex items-center justify-between gap-2 pl-3 text-[10px] text-[var(--text-muted)]">
        <span className="truncate">{plainPreview(session.preview) || '还没有内容'}</span>
        <span className="shrink-0 tabular-nums">{relative}</span>
      </span>
      {session.id ? (
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onDelete(session);
          }}
          className="absolute right-1.5 top-1.5 grid h-6 w-6 place-items-center rounded text-[var(--text-muted)] opacity-0 transition hover:bg-[var(--danger-bg)] hover:text-[var(--danger)] group-hover:opacity-100"
          aria-label={`删除 ${session.title}`}
          title={`删除 ${session.title}`}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      ) : null}
    </div>
  );
});
