import { useMutation, useQueryClient } from '@tanstack/react-query';
import { getApiClient, type RequestOptions } from '@qzdap/web-api';
import { normalizeError } from '@/api/shared/http-error';

type Action = { path: string; method?: RequestOptions['method']; body?: unknown; success?: string; onSuccess?: () => void };

/** Business writes always await the server; React state is never a substitute for persistence. */
export function useServerAction(notify: (text: string) => void) {
  const client = useQueryClient();
  return useMutation<unknown, unknown, Action>({
    mutationKey: ['server-action'],
    meta: { pathname: typeof window === 'undefined' ? '' : window.location.pathname },
    mutationFn: ({ path, method = 'POST', body }) => getApiClient().request(path, { method, body }),
    onSuccess: async (_, action) => {
      await client.invalidateQueries();
      action.onSuccess?.();
      if (action.success) notify(action.success);
    },
    onError: (error) => notify(`请求失败：${normalizeError(error).message}`),
  });
}
