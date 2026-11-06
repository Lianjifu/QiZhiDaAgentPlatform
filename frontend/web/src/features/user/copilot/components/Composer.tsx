/**
 * 输入区 ✓ —— 文本 + 附件 + 快捷命令 + 提及 ✓。
 *
 * ⚠️ **附件一律真上传** ✓ —— 没有会话时**明确拒绝** ✓（不假装成功 ✓）。
 */
import { ArrowUp, Paperclip, Square } from 'lucide-react';
import { memo, useState } from 'react';

const COMPOSER_OPTIONS = {
  slash: [
    { label: '/整理', value: '/整理 ' },
    { label: '/总结', value: '/总结 ' },
    { label: '/生成', value: '/生成 ' },
  ],
  mention: [
    { label: '@智能体', value: '@智能体 ' },
    { label: '@团队成员', value: '@团队成员 ' },
    { label: '@知识库', value: '@知识库 ' },
  ],
} as const;

export type ComposerProps = {
  input: string;
  onInputChange: (value: string) => void;
  onSubmit: () => void;
  onStop: () => void;
  isSending: boolean;
  onAttach: (file: File) => void;
};

/**
 * ⚠️ **记忆化** ✓ —— 流式时每个 chunk 都重渲染整页 ✓ —— 输入框不该跟着动 ✓
 * （它一个字都没变 ✓ —— 而且受控 textarea 重渲染多了会**丢光标** ✗✗）。
 */
export const Composer = memo(function Composer({
  input,
  onInputChange,
  onSubmit,
  onStop,
  isSending,
  onAttach,
}: ComposerProps) {
  const [menu, setMenu] = useState<'slash' | 'mention' | null>(null);

  const selectOption = (value: string) => {
    onInputChange(`${input.slice(0, -1)}${value}`);
    setMenu(null);
  };

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
      className="w-full"
    >
      {menu ? (
        <div
          role="status"
          aria-live="polite"
          className="mb-2 rounded-xl border border-[var(--border)] bg-[var(--surface-1)] p-2 shadow-[var(--shadow-xs)]"
        >
          <div className="flex items-center justify-between px-2 pb-2 text-[10px] text-[var(--text-muted)]">
            <span className="font-semibold text-[var(--text-secondary)]">
              {menu === 'slash' ? '快捷命令' : '提及对象'}
            </span>
            <span>已识别 {menu === 'slash' ? '/' : '@'}</span>
          </div>
          <div
            role="listbox"
            aria-label={menu === 'slash' ? '快捷命令列表' : '提及对象列表'}
            className="flex gap-1 overflow-x-auto"
          >
            {COMPOSER_OPTIONS[menu].map((option) => (
              <button
                key={option.label}
                type="button"
                role="option"
                aria-selected="false"
                onClick={() => selectOption(option.value)}
                className="shrink-0 rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs text-[var(--text-secondary)] hover:border-[var(--brand)] hover:bg-[var(--brand-light)] hover:text-[var(--brand)]"
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      ) : null}
      <div className="flex items-end gap-2 rounded-2xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] p-2 shadow-[var(--shadow-xs)] focus-within:border-[var(--brand)]">
        <button
          type="button"
          className="rounded-lg p-2 text-[var(--text-muted)] hover:bg-[var(--bg-hover)]"
          aria-label="添加附件"
          onClick={() => document.getElementById('copilot-file-input')?.click()}
        >
          <Paperclip className="h-4 w-4" />
          <input
            type="file"
            className="hidden"
            id="copilot-file-input"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) {
                onAttach(file);
                setMenu(null);
                event.currentTarget.value = '';
              }
            }}
          />
        </button>
        <textarea
          value={input}
          onChange={(event) => {
            const value = event.target.value;
            onInputChange(value);
            if (value.endsWith('/') || value.endsWith('@')) {
              setMenu(value.endsWith('/') ? 'slash' : 'mention');
            } else {
              setMenu(null);
            }
          }}
          onKeyDown={(event) => {
            if (event.key === 'Escape' && menu) {
              event.preventDefault();
              setMenu(null);
              return;
            }
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              onSubmit();
            }
          }}
          rows={1}
          placeholder="描述你想完成的工作..."
          className="max-h-32 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none placeholder:text-[var(--text-muted)]"
        />
        {isSending ? (
          <button
            type="button"
            onClick={onStop}
            className="grid h-9 w-9 place-items-center rounded-lg border border-[var(--border)] bg-[var(--surface-1)] text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]"
            aria-label="停止生成"
            title="停止生成"
          >
            <Square className="h-3.5 w-3.5 fill-current" />
          </button>
        ) : (
          <button
            type="submit"
            disabled={!input.trim()}
            className="grid h-9 w-9 place-items-center rounded-lg bg-[var(--brand)] text-white disabled:cursor-not-allowed disabled:opacity-40"
            aria-label="发送消息"
          >
            <ArrowUp className="h-4 w-4" />
          </button>
        )}
      </div>
      <p className="mt-2 text-center text-[10px] text-[var(--text-muted)]">
        智能体可能会出错，请检查重要结果和来源。
      </p>
    </form>
  );
});
