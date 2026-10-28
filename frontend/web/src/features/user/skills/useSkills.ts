import { useApiQuery, useApiMutation } from '@/services/query';
import { qk } from '@/api/shared/query-keys';
import { withDefaults } from '@/api/shared/pagination';
import type { Capability, SkillListParams, ToggleFavoriteVars, RecordUseVars } from './schema';

const PATH = '/api/catalog/skills';

export function useCapabilities(params: SkillListParams = {}) {
  const query = withDefaults(params);
  return useApiQuery<Capability[]>(
    [...qk.user.skills.list],
    PATH,
    { query },
    { staleTime: 15_000, placeholderData: (prev) => prev },
  );
}

export function useCapability(id: string | null) {
  return useApiQuery<Capability>(
    [...qk.user.skills.detail(id ?? 'none')],
    id ? `${PATH}/${id}` : `${PATH}/__noop__`,
    undefined,
    { enabled: Boolean(id), staleTime: 15_000 },
  );
}

export function useToggleFavorite() {
  return useApiMutation<Capability, ToggleFavoriteVars>(
    (vars) => `${PATH}/${vars.id}/favorite`,
    { invalidateKeys: [qk.user.skills.root] },
    'POST',
  );
}

export function useRecordUse() {
  return useApiMutation<{ id: string; recordedAt: string }, RecordUseVars>(
    (vars) => `${PATH}/${vars.id}/record-use`,
    { invalidateKeys: [qk.user.skills.recent, qk.user.skills.root] },
    'POST',
  );
}
