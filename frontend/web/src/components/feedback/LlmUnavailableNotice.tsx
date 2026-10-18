/**
 * 全局 LLM 未配置 banner — 监听 React Query 错误缓存, 一旦发现
 * code === "PROVIDER_UNAVAILABLE" 或 HTTP 503, 在页面顶部显示一条
 * 引导横幅, 跳到 /admin/models/new 去配真实 LLM 供应商.
 *
 * 设计上与 ApiFailureNotice 互补: 那个显示"请求失败"的红色 toast,
 * 这个显示"为什么失败 + 怎么修"的黄色 banner. 用户可手动 dismiss
 * (本会话内不再弹), 但下次 reload 会重新出现.
 */
import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { AlertTriangle, X } from 'lucide-react';
import { normalizeError } from '@/api/shared/http-error';

const STORAGE_KEY = 'qzdap.llm_unavailable.dismissed_at';
const DISMISS_TTL_MS = 60 * 60 * 1000; // 1 小时内不重复弹

function isLlmUnavailableError(err: unknown): boolean {
  const norm = normalizeError(err);
  if (!norm) return false;
  if (norm.code === 'PROVIDER_UNAVAILABLE') return true;
  if (norm.status === 503) {
    // 兜底: 任何 503 都先当作 LLM 未配置 (ProviderUnavailable 是平台目前
    // 唯一会返回 503 的路径), 不然会漏掉非 code 的旧调用.
    return true;
  }
  return false;
}

function isDismissed(): boolean {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return false;
    const ts = Number(raw);
    if (!Number.isFinite(ts)) return false;
    return Date.now() - ts < DISMISS_TTL_MS;
  } catch {
    return false;
  }
}

function markDismissed(): void {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, String(Date.now()));
  } catch {
    /* sessionStorage 不可用时静默忽略, 下次 reload 仍会弹 */
  }
}

export function LlmUnavailableNotice() {
  const client = useQueryClient();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (isDismissed()) return;
    let cancelled = false;
    const check = () => {
      if (cancelled || isDismissed()) return;
      const queries = client.getQueryCache().getAll();
      const hit = queries.some((q) => q.state.status === 'error' && isLlmUnavailableError(q.state.error));
      if (hit) setVisible(true);
    };
    check();
    const stop = client.getQueryCache().subscribe(check);
    const stopMut = client.getMutationCache().subscribe(check);
    return () => { cancelled = true; stop(); stopMut(); };
  }, [client]);

  if (!visible) return null;

  const handleDismiss = () => {
    markDismissed();
    setVisible(false);
  };

  return (
    <div
      role="alert"
      data-testid="llm-unavailable-banner"
      className="sticky top-0 z-50 flex items-center gap-3 border-b border-amber-300 bg-amber-50 px-4 py-2.5 text-sm text-amber-900 shadow-sm"
    >
      <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600" aria-hidden="true" />
      <span className="flex-1">
        当前环境未配置 LLM 供应商, 任何调用都会返回 503。请到
        <Link
          to="/admin/models/new"
          className="mx-1.5 inline-flex items-center gap-1 rounded-md border border-amber-400 bg-amber-100 px-2 py-0.5 font-semibold text-amber-900 hover:bg-amber-200"
        >
          模型管理 → 新建供应商
        </Link>
        配置 API key 后刷新页面即可使用。
      </span>
      <button
        type="button"
        onClick={handleDismiss}
        aria-label="关闭提示"
        className="grid h-7 w-7 place-items-center rounded-md text-amber-700 hover:bg-amber-200"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
