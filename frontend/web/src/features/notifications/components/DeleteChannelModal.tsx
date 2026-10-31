import { Trash2 } from 'lucide-react';
import { CenterModal } from '@/components/feedback/CenterModal';
import type { NotificationChannel } from '../schema';
import { KIND_META } from './constants';

interface DeleteChannelModalProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  channel: NotificationChannel | null;
  pending?: boolean;
}

/** 删渠道的二次确认 —— 删了就没了,先说清楚影响。 */
export function DeleteChannelModal({
  open,
  onClose,
  onConfirm,
  channel,
  pending = false,
}: DeleteChannelModalProps) {
  if (!channel) return null;
  return (
    <CenterModal
      open={open}
      onClose={onClose}
      ariaLabel="删除通知渠道"
      panelClassName="max-w-md"
      title={
        <span className="flex items-center gap-2">
          <Trash2 className="h-5 w-5 text-rose-600" />
          删除渠道:{channel.name}
        </span>
      }
      description="确认后将永久删除该渠道,飞书 / 企业微信 / 钉钉侧的应用配置不会被改动。"
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-[var(--border)] px-4 py-2 text-xs font-semibold"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={pending}
            className="rounded-xl bg-rose-600 px-4 py-2 text-xs font-semibold text-white disabled:opacity-50"
          >
            {pending ? '删除中…' : '确认删除'}
          </button>
        </>
      }
    >
      <div className="mt-4 space-y-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-xs text-rose-900 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">
        <p>· 类型:{KIND_META[channel.kind].label}</p>
        <p>· 目标:{channel.target || '—'}</p>
        <p>· 状态:{channel.status === 'active' ? '已启用' : '已暂停'}</p>
        <p>· 今日会话:{channel.sentToday}</p>
      </div>
    </CenterModal>
  );
}
