/**
 * InteractiveToastHost — 右下 toast 队列.
 *
 * info / success 自动 3-4s 消失; warn 6s; error 长显 (需用户手动关).
 * 进度条显示 ttl 倒计时.
 */
import { useEffect } from 'react';
import { AlertCircle, AlertTriangle, CheckCircle, Info, X } from 'lucide-react';
import type { ToastMsg } from '../interactiveStore';

const ICONS = {
  info: Info,
  success: CheckCircle,
  warn: AlertTriangle,
  error: AlertCircle,
} as const;

const TONE = {
  info: 'border-sky-200 bg-sky-50 text-sky-900',
  success: 'border-emerald-200 bg-emerald-50 text-emerald-900',
  warn: 'border-amber-300 bg-amber-50 text-amber-900',
  error: 'border-rose-300 bg-rose-50 text-rose-900',
} as const;

export function InteractiveToastHost({
  toasts,
  onDismiss,
}: {
  toasts: ToastMsg[];
  onDismiss: (id: string) => void;
}) {
  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-full max-w-sm flex-col gap-2"
    >
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} onDismiss={() => onDismiss(t.id)} />
      ))}
    </div>
  );
}

function ToastItem({
  toast,
  onDismiss,
}: {
  toast: ToastMsg;
  onDismiss: () => void;
}) {
  const Icon = ICONS[toast.level] ?? Info;
  const tone = TONE[toast.level] ?? TONE.info;
  const hasTtl = toast.ttl_ms !== undefined;

  // 进度条: 长显的 toast 不渲染进度条
  useEffect(() => {
    // no-op; 自动 dismiss 由 store 处理
  }, []);

  return (
    <div
      role="status"
      className={`pointer-events-auto relative overflow-hidden rounded-xl border ${tone} px-4 py-3 shadow-[var(--shadow-sm)]`}
    >
      <div className="flex items-start gap-2">
        <Icon className="mt-0.5 h-4 w-4 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold leading-5">{toast.title}</p>
          {toast.body && (
            <p className="mt-1 text-[11px] leading-5 opacity-90">{toast.body}</p>
          )}
        </div>
        <button
          type="button"
          onClick={onDismiss}
          aria-label="关闭通知"
          className="rounded-md p-0.5 opacity-60 hover:opacity-100"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      {hasTtl && toast.ttl_ms && (
        <div
          className="absolute bottom-0 left-0 h-0.5 bg-current opacity-40"
          style={{
            width: '100%',
            animation: `toast-progress ${toast.ttl_ms}ms linear forwards`,
          }}
        />
      )}
      <style>{`
        @keyframes toast-progress {
          from { width: 100%; }
          to { width: 0; }
        }
      `}</style>
    </div>
  );
}