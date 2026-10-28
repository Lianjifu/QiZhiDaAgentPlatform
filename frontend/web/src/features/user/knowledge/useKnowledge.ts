/**
 * 用户侧「我的知识」hooks — 列表来自管理端已开放知识库文档的 catalog 投影。
 */
import { useApiQuery, useApiMutation } from '@/services/query';
import { qk } from '@/api/shared/query-keys';
import { withDefaults } from '@/api/shared/pagination';
import type {
  KnowledgeResource,
  KnowledgeListParams,
  AskQuestionVars,
} from './schema';

const PATH = '/api/catalog/knowledge';

export function useKnowledgeResources(params: KnowledgeListParams = {}) {
  const query = withDefaults(params);
  return useApiQuery<KnowledgeResource[]>(
    [...qk.user.knowledge.list],
    PATH,
    { query },
    { staleTime: 15_000, placeholderData: (prev) => prev },
  );
}

export function useAskQuestion() {
  return useApiMutation<{ question: string; resourceId: string }, AskQuestionVars>(
    () => `${PATH}/ask`,
    { invalidateKeys: [qk.user.knowledge.history] },
    'POST',
  );
}

export function useToggleKnowledgeFavorite() {
  return useApiMutation<KnowledgeResource, { id: string; on: boolean }>(
    (vars) => `${PATH}/${vars.id}/favorite`,
    { invalidateKeys: [qk.user.knowledge.root] },
    'POST',
  );
}
