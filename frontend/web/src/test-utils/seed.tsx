/**
 * 测试辅助 — 在 QueryClient 缓存里预置页面所需的 fixture 数据,
 * 让 `useApiQuery` 不必真正调用 getApiClient (测试环境未初始化)。
 */
import type { QueryClient } from '@tanstack/react-query';
import { QueryClient as QC, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { render, type RenderOptions, type RenderResult } from '@testing-library/react';
import type { ReactElement, ReactNode } from 'react';
import { apiQueryKey } from '@/services/query';

/**
 * 页面查询的**完整** query key.
 *
 * 直接调 `apiQueryKey` —— 那是 `useApiQuery` 用的同一个算法. 别在测试里
 * 手拼 key: 以前手拼的形状少了 `runtimeStorageKey('query')` 那一段,
 * 预置的数据页面根本读不到 (缓存 miss → 页面空白), 而且这种错**不会报错**,
 * 只会让 40 个测试文件集体变红.
 */
export function pageQueryKey(
  path: readonly unknown[],
  opts?: { workspaceId?: string },
): readonly unknown[] {
  return apiQueryKey(path, opts);
}

export function seedPageQueryData<T>(
  qc: QueryClient,
  qkPath: readonly unknown[],
  data: T,
  opts?: { workspaceId?: string },
) {
  qc.setQueryData(apiQueryKey(qkPath, opts), data as unknown);
}

/** 通用:把任意最终 key 形态注入到缓存 (不附加 workspaceId)。 */
export function seedRaw<T>(
  qc: QueryClient,
  finalKey: readonly unknown[],
  data: T,
) {
  qc.setQueryData(finalKey, data as unknown);
}

export interface RenderWithProvidersOptions extends Omit<RenderOptions, 'wrapper'> {
  seeds?: Array<{ key: readonly unknown[]; data: unknown }>;
  initialEntries?: string[];
}

export function createTestQueryClient() {
  return new QC({ defaultOptions: { queries: { retry: false } } });
}

export function renderWithProviders(
  ui: ReactElement,
  { seeds = [], initialEntries, ...rest }: RenderWithProvidersOptions = {},
): RenderResult {
  const qc = createTestQueryClient();
  for (const seed of seeds) {
    qc.setQueryData(seed.key, seed.data as unknown);
  }
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
    </QueryClientProvider>,
    rest,
  );
}

export function ProvidersWrapper({ children, qc }: { children: ReactNode; qc: QueryClient }) {
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}