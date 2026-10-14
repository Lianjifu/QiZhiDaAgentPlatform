/**
 * 管理侧「新建技能」— 路由 /admin/tools/new
 *
 * - 无 type 参数:展示 3 选 1 的 type picker(让用户先选类型)
 * - 带 type 参数:直接进入 wizard,type 锁定
 *
 * 顶栏面包屑为「技能管理 > 新建页」。
 */
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useState } from 'react';
import { normalizeError } from '@/api/shared/http-error';
import type { Skill, SkillType } from './schema';
import { useCreateSkill } from './useAdminSkills';
import { CreateSkillWizard } from './components/CreateSkillWizard';
import { SkillTypePicker } from './components/SkillTypePicker';

function isSkillType(value: string | null): value is SkillType {
  return value === 'Skill' || value === 'Tool' || value === 'MCP';
}

export default function SkillCreatePage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const typeParam = params.get('type');
  const locked = isSkillType(typeParam);
  const type: SkillType = locked ? typeParam : 'Skill';
  const create = useCreateSkill();
  const [error, setError] = useState('');

  const handleCreate = (skill: Skill) => {
    setError('');
    create.mutate({
      id: skill.id,
      name: skill.name,
      type: skill.type,
      description: skill.description,
      owner: skill.owner,
      risk: skill.risk,
      needConfirm: skill.needConfirm,
      inputSchema: skill.inputSchema,
      outputSchema: skill.outputSchema,
      profile: skill.profile,
      runtime: skill.runtime,
    }, {
      onSuccess: (created) => navigate(`/admin/tools/${created.id}`),
      onError: (cause) => setError(normalizeError(cause).message),
    });
  };

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-4 p-5 pb-16 sm:p-8 xl:px-6">
      {error && <p role="alert" className="rounded-xl border border-rose-300 bg-rose-50 px-4 py-3 text-sm text-rose-700">创建失败：{error}</p>}
      {locked ? (
        <CreateSkillWizard
          open
          embedded
          type={type}
          lockType
          onClose={() => navigate('/admin/tools')}
          onCreate={handleCreate}
        />
      ) : (
        <SkillTypePicker />
      )}
    </div>
  );
}
