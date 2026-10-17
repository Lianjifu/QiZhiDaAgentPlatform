import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useLocation } from 'react-router-dom';
import { normalizeError } from '@/api/shared/http-error';

/** Covers every API consumer, including drawers and auxiliary queries. */
export function ApiFailureNotice() {
  const client = useQueryClient();
  const { pathname } = useLocation();
  const [errors, setErrors] = useState<string[]>([]);
  useEffect(() => {
    // 把 setState 推到下一个 task (setTimeout 0), 不能用 queueMicrotask —
    // 缓存订阅可能在另一个组件 (e.g. LoginPage) 的 render 期间同步触发,
    // 微任务仍在 React 18 同一批 commit 内, setState 仍会触发 "setState in render"
    // 警告并让目标组件在严格模式下卡死. setTimeout 跳出当前任务, 不会和 render
    // 阶段重叠.
    const update = () => {
      setTimeout(() => {
        const queries = client.getQueryCache().getAll().filter((q) => q.getObserversCount() > 0 && q.state.status === 'error');
        const allMutations = client.getMutationCache().getAll();
        const latest = new Map<string, (typeof allMutations)[number]>();
        for (const mutation of allMutations) {
          if (mutation.options.meta?.pathname !== pathname) continue;
          const action = mutation.state.variables as { path?: string; method?: string } | undefined;
          const key = JSON.stringify([mutation.options.mutationKey, action?.path, action?.method]);
          const previous = latest.get(key);
          if (!previous || previous.state.submittedAt <= mutation.state.submittedAt) latest.set(key, mutation);
        }
        const mutations = [...latest.values()].filter((m) => m.state.status === 'error');
        setErrors([...new Set([...queries.map((q) => normalizeError(q.state.error).message), ...mutations.map((m) => normalizeError(m.state.error).message)])]);
      }, 0);
    };
    update();
    const stopQueries = client.getQueryCache().subscribe(update);
    const stopMutations = client.getMutationCache().subscribe(update);
    return () => { stopQueries(); stopMutations(); };
  }, [client, pathname]);
  if (!errors.length) return null;
  return <div role="alert" className="fixed bottom-5 left-1/2 z-[100] max-h-48 w-[min(90vw,720px)] -translate-x-1/2 overflow-auto rounded-xl border border-rose-300 bg-rose-50 px-4 py-3 text-sm text-rose-700 shadow-lg">{errors.map((error) => <p key={error}>请求失败：{error}</p>)}</div>;
}
