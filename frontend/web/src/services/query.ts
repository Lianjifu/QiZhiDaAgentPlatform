/**
 * 通用 TanStack Query 封装 — 统一错误处理 / 鉴权注入
 */
import { useQuery, useMutation, useQueryClient, type UseQueryOptions, type UseMutationOptions } from '@tanstack/react-query';
import { getApiClient } from '@qzdap/web-api';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { runtimeStorageKey } from '@/lib/environment';

/**
 * 查询 key 的**唯一**算法 —— 所有 useApiQuery 都走这里, 单测预置缓存也走这里.
 *
 * 形状固定为 `[...key, workspaceId, runtimeStorageKey('query')]`:
 *
 * * ``workspaceId``  当前工作区.
 * * ``runtimeStorageKey('query')``  按业务环境隔离 (演示/开发各一份缓存).
 *
 * **查询参数不进 key** —— 每个页面都是拿到整份列表再在客户端过滤
 * (后端那些 catalog 端点本来也不支持过滤参数), 所以按过滤条件切 key
 * 只会让缓存碎片化、白白多发请求. 请求参数照传, 只是不参与缓存身份.
 */
export function apiQueryKey(
  key: readonly unknown[],
  opts?: { workspaceId?: string },
): readonly unknown[] {
  return [...key, opts?.workspaceId ?? 'w1', runtimeStorageKey('query')];
}

export function useApiQuery<T>(
  key: readonly unknown[],
  path: string,
  params?: { query?: Record<string, any>; body?: unknown; method?: 'GET' | 'POST' },
  options?: Omit<UseQueryOptions<T>, 'queryKey' | 'queryFn'>,
) {
  const workspaceId = useWorkspaceStore((state) => state.currentWorkspaceId ?? 'w1');
  const q = useQuery<T>({
    queryKey: apiQueryKey(key, { workspaceId }),
    queryFn: async () => {
      const c = getApiClient();
      return c.request<T>(path, {
        method: params?.method ?? 'GET',
        query: params?.query,
        body: params?.body,
      });
    },
    ...options,
    placeholderData: undefined,
  });
  return {
    data: q.isError || q.data === null ? undefined : q.data,
    error: q.error,
    isLoading: q.isLoading,
    isFetching: q.isFetching,
    isError: q.isError,
    refetch: q.refetch,
  };
}

type MutationOpts<TData, TVar> = {
  onSuccess?: (data: TData, vars: TVar) => void;
  onError?: (err: unknown, vars: TVar) => void;
  /** 精确失效的 query key 前缀；未指定时仍全量 invalidate（兼容旧行为） */
  invalidateKeys?: readonly (readonly unknown[])[];
};

export function useApiMutation<TData, TVar>(
  path: string | ((vars: TVar) => string),
  options?: MutationOpts<TData, TVar>,
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE' = 'POST',
) {
  const qc = useQueryClient();
  const pathname = typeof window === 'undefined' ? '' : window.location.pathname;
  // 4 个泛型让 TanStack Query 类型完整
  return useMutation<TData, unknown, TVar>({
    mutationKey: [method, String(path)],
    meta: { pathname },
    mutationFn: async (vars: TVar) => {
      const c = getApiClient();
      const p = typeof path === 'function' ? path(vars) : path;
      return c.request<TData>(p, { method, body: vars });
    },
    onSuccess: (data, vars) => {
      options?.onSuccess?.(data, vars);
      if (options?.invalidateKeys?.length) {
        for (const key of options.invalidateKeys) {
          qc.invalidateQueries({ queryKey: key });
        }
      } else {
        qc.invalidateQueries();
      }
    },
    onError: (err, vars) => {
      options?.onError?.(err, vars);
    },
  } as UseMutationOptions<TData, unknown, TVar>);
}

/** multipart 文件上传（FormData） */
export function useApiUploadMutation<TData>(
  path: string,
  options?: MutationOpts<TData, FormData>,
) {
  const qc = useQueryClient();
  const pathname = typeof window === 'undefined' ? '' : window.location.pathname;
  return useMutation<TData, unknown, FormData>({
    mutationKey: ['upload', path],
    meta: { pathname },
    mutationFn: async (form: FormData) => getApiClient().upload<TData>(path, form),
    onSuccess: (data, vars) => {
      options?.onSuccess?.(data, vars);
      qc.invalidateQueries();
    },
    onError: (err, vars) => {
      options?.onError?.(err, vars);
    },
  } as UseMutationOptions<TData, unknown, FormData>);
}
