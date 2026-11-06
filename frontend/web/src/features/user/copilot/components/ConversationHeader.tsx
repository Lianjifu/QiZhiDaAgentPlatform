/**
 * **对话头部** ✓ —— 智能体 / 能力 / 模型 / 状态 / 轮次 ✓。
 *
 * ⚠️ **「当前智能体」原来浮在消息流中间** ✓（滚着滚着就找不着了 ✗✗）——
 * 现在收进头部 ✓。
 * ⚠️ **名字是真的** ✓ —— 来自会话元数据 ✓（后端写的 ✓）；没有智能体就写
 * 「未选择智能体」✓ —— 不编一个「工作重点梳理」✗✗。
 */
import { Bot, Menu, Sparkles } from 'lucide-react';
import { Link } from 'react-router-dom';

export type ConversationHeaderProps = {
  agentName?: string;
  skillName?: string;
  model?: string;
  status?: 'idle' | 'running' | 'waiting_approval';
  turnCount?: number;
  onOpenSessions?: () => void;
};

const STATUS_TEXT: Record<'idle' | 'running' | 'waiting_approval', string> = {
  idle: '就绪',
  running: '生成中',
  waiting_approval: '等你确认',
};

const STATUS_CLASS: Record<'idle' | 'running' | 'waiting_approval', string> = {
  idle: 'bg-slate-100 text-[var(--text-muted)]',
  running: 'bg-[var(--brand-light)] text-[var(--brand)]',
  waiting_approval: 'bg-amber-100 text-amber-800',
};

export function ConversationHeader({
  agentName,
  skillName,
  model,
  status = 'idle',
  turnCount,
  onOpenSessions,
}: ConversationHeaderProps) {
  const title = agentName ? `与${agentName}对话` : '新对话';
  return (
    <header className="flex min-h-14 items-center justify-between gap-3 border-b border-[var(--border)] bg-[var(--surface-1)] px-4 sm:px-6">
      <div className="flex min-w-0 items-center gap-3">
        {onOpenSessions ? (
          <button
            type="button"
            className="rounded-md p-2 text-[var(--text-muted)] hover:bg-[var(--bg-hover)] lg:hidden"
            aria-label="打开对话列表"
            onClick={onOpenSessions}
          >
            <Menu className="h-4 w-4" />
          </button>
        ) : null}
        <div className="min-w-0">
          <h1 className="truncate text-sm font-semibold">{title}</h1>
          <p className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-[var(--text-muted)]">
            <span className="inline-flex items-center gap-1">
              <Bot className="h-3 w-3" aria-hidden="true" />
              {agentName || '未选择智能体'}
            </span>
            {skillName ? (
              <span className="inline-flex items-center gap-1">
                <Sparkles className="h-3 w-3" aria-hidden="true" />
                {skillName}
              </span>
            ) : null}
            {model ? <span className="font-mono">{model}</span> : null}
          </p>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <span
          className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_CLASS[status]}`}
        >
          {STATUS_TEXT[status]}
        </span>
        {turnCount != null ? (
          <span className="hidden text-[11px] text-[var(--text-muted)] sm:inline">
            {turnCount} 轮
          </span>
        ) : null}
        <Link
          to="/library?tab=agents"
          className="rounded-lg border border-[var(--border)] px-2.5 py-1 text-[11px] font-medium text-[var(--text-secondary)] transition hover:border-[var(--brand)] hover:text-[var(--brand)]"
        >
          更换智能体
        </Link>
      </div>
    </header>
  );
}
