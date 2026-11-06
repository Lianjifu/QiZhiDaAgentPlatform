/**
 * 路由预览链 —— 展示这条规则解析后的主备顺序 ✓
 * （``GET /api/admin/models/routes/{id}/preview-chain`` ✓ —— **不发请求** ✓
 * 不消耗额度 ✓）。
 */
import { CenterModal } from '@/components/feedback/CenterModal';
import type { RouteChain } from '../schema';

export interface RouteChainModalProps {
  open: boolean;
  onClose: () => void;
  chain: RouteChain | undefined;
  loading?: boolean;
}

export function RouteChainModal({ open, onClose, chain, loading }: RouteChainModalProps) {
  return (
    <CenterModal
      open={open}
      onClose={onClose}
      ariaLabel="路由预览链"
      title="路由预览链"
      description={
        chain ? `${chain.routeName} · 策略 ${chain.strategy}` : '按当前规则解析模型顺序（不发请求）。'
      }
      footer={
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg border border-[var(--border)] px-3 py-2 text-xs font-semibold"
        >
          关闭
        </button>
      }
    >
      <div className="mt-4">
        {loading ? (
          <p className="py-6 text-center text-xs text-[var(--text-muted)]">正在解析…</p>
        ) : !chain || chain.chain.length === 0 ? (
          <p className="py-6 text-center text-xs text-[var(--text-muted)]">这条规则还没有可用的模型。</p>
        ) : (
          <ol className="space-y-2">
            {chain.chain.map((model, index) => (
              <li
                key={model.id}
                className="flex items-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] px-3 py-2 text-xs"
              >
                <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-[var(--surface-1)] text-[10px] font-semibold text-[var(--text-muted)]">
                  {index + 1}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block font-semibold">
                    {model.name}
                    {model.isPrimary ? (
                      <span className="ml-2 rounded-full bg-[var(--brand-light)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--brand)]">
                        主
                      </span>
                    ) : null}
                  </span>
                  {model.upstreamModel ? (
                    <span className="mt-0.5 block truncate text-[11px] text-[var(--text-muted)]">
                      {model.upstreamModel}
                    </span>
                  ) : null}
                </span>
                <span className="shrink-0 text-[11px] tabular-nums text-[var(--text-muted)]">
                  {model.successRate !== null ? `${model.successRate}%` : '—'}
                  {model.latencyMs !== null ? ` · ${model.latencyMs}ms` : ''}
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </CenterModal>
  );
}
