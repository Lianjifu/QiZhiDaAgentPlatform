/**
 * **失败卡片** ✓ —— 这一轮没跑出来 ✓。
 *
 * ⚠️ **失败要说清楚 + 能重试** ✓ —— 之前失败只冒一行黄字 ✓（还把所有人
 * 都指向「智能体库」✗✗ —— 供应商没配跟智能体库没关系 ✗✗）。
 */
import { AlertTriangle, RotateCcw } from 'lucide-react';

export type FailureCardProps = {
  title: string;
  message: string;
  code?: string;
  onRetry?: () => void;
  retrying?: boolean;
};

export function FailureCard({ title, message, code, onRetry, retrying }: FailureCardProps) {
  return (
    <div
      role="alert"
      className="rounded-xl border border-rose-200 bg-rose-50/70 px-4 py-3 text-xs text-rose-900"
    >
      <p className="flex flex-wrap items-center gap-2 font-semibold">
        <AlertTriangle className="h-3.5 w-3.5 text-rose-600" aria-hidden="true" />
        {title}
        {code ? (
          <span className="rounded bg-rose-100 px-1.5 py-0.5 font-mono text-[10px] text-rose-700">
            {code}
          </span>
        ) : null}
      </p>
      <p className="mt-1.5 leading-5 text-rose-800">{message}</p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          disabled={retrying}
          className="mt-2.5 inline-flex items-center gap-1.5 rounded-lg border border-rose-300 bg-white px-2.5 py-1 font-semibold text-rose-700 transition hover:bg-rose-100 disabled:opacity-60"
        >
          <RotateCcw className="h-3 w-3" aria-hidden="true" />
          {retrying ? '重试中…' : '重试这一轮'}
        </button>
      ) : null}
    </div>
  );
}
