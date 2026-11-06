/**
 * **最近对话** 列表 ✓。
 *
 * ⚠️ **记忆化** ✓ —— 流式时每个 chunk 都重渲染整页 ✓ —— 侧栏不该跟着动 ✓
 * （它一个字都没变 ✓）。
 */
import { memo } from 'react';
import type { CopilotSession } from '../schema';
import { SessionListItem } from './SessionListItem';

export type SessionListProps = {
  sessions: CopilotSession[];
  activeId?: string;
  search?: string;
  onSelect: (session: CopilotSession) => void;
  onDelete: (session: CopilotSession) => void;
};

export const SessionList = memo(function SessionList({
  sessions,
  activeId,
  search,
  onSelect,
  onDelete,
}: SessionListProps) {
  return (
    <div className="flex-1 overflow-auto px-2">
      <p className="px-2 py-2 text-[11px] font-semibold text-[var(--text-muted)]">最近对话</p>
      {sessions.length === 0 ? (
        <p className="px-2 py-3 text-[11px] leading-5 text-[var(--text-muted)]">
          {search ? '没有匹配的对话。' : '还没有对话 —— 问一句就开始。'}
        </p>
      ) : null}
      {sessions.map((item) => (
        <SessionListItem
          key={item.id ?? item.title}
          session={item}
          active={activeId === item.id}
          onSelect={onSelect}
          onDelete={onDelete}
        />
      ))}
    </div>
  );
});
