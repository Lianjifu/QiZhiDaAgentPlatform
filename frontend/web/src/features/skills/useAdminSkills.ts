import { useApiQuery, useApiMutation } from '@/services/query';
import { qk } from '@/api/shared/query-keys';
import { withDefaults } from '@/api/shared/pagination';
import type {
  Skill,
  AdminSkillListParams,
  CreateSkillVars,
  UpdateSkillVars,
  DeleteSkillVars,
  BulkPublishVars,
} from './schema';

const ROOT = '/api/admin/skills';

export function useAdminSkills(params: AdminSkillListParams = {}) {
  const query = withDefaults(params);
  return useApiQuery<Skill[]>(
    [...qk.admin.skills.list],
    ROOT,
    { query },
    { staleTime: 15_000, placeholderData: (prev) => prev },
  );
}

export function useAdminSkill(id: string | null) {
  return useApiQuery<Skill>(
    [...qk.admin.skills.detail(id ?? 'none')],
    id ? `${ROOT}/${id}` : `${ROOT}/__noop__`,
    undefined,
    { enabled: Boolean(id), staleTime: 30_000 },
  );
}

export function useCreateSkill() {
  return useApiMutation<Skill, CreateSkillVars>(
    ROOT,
    { invalidateKeys: [qk.admin.skills.root] },
    'POST',
  );
}

export function useUpdateSkill() {
  return useApiMutation<Skill, UpdateSkillVars>(
    (vars) => `${ROOT}/${vars.id}`,
    { invalidateKeys: [qk.admin.skills.root] },
    'PATCH',
  );
}

export function useDeleteSkill() {
  return useApiMutation<{ ok: true; id: string }, DeleteSkillVars>(
    (vars) => `${ROOT}/${vars.id}`,
    { invalidateKeys: [qk.admin.skills.root] },
    'DELETE',
  );
}

export function useBulkPublish() {
  return useApiMutation<{ affected: number }, BulkPublishVars>(
    `${ROOT}/bulk`,
    { invalidateKeys: [qk.admin.skills.root] },
    'POST',
  );
}