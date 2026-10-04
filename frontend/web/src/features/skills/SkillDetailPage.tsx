/**
 * 管理侧「技能详情」— 路由 /admin/tools/:id
 *
 * 详情与编辑合并：默认只读，右上角「编辑」进入修改；`/edit` 与 `?edit=1` 等价。
 */
import { useEffect, useState } from 'react';
import { Navigate, useLocation, useParams, useSearchParams } from 'react-router-dom';
import type { Skill } from './schema';
import type { DrawerPanel } from './components/constants';
import { SkillWorkspace } from './components/SkillWorkspace';
import { useAdminSkill, useUpdateSkill } from './useAdminSkills';

function NotFound() {
  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-4 p-5 pb-16 sm:p-8 xl:px-6">
      <div className="rounded-2xl border border-dashed border-[var(--border)] bg-[var(--surface-1)] p-8 text-center">
        <p className="text-sm font-semibold">技能不存在或已被删除</p>
        <p className="mt-1 text-xs text-[var(--text-muted)]">请返回列表重新选择。</p>
      </div>
    </div>
  );
}

export default function SkillDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const location = useLocation();
  const [params, setSearchParams] = useSearchParams();
  const editing = params.get('edit') === '1';
  const { data: skill, isLoading, isError } = useAdminSkill(id || null);
  const update = useUpdateSkill();
  const [draft, setDraft] = useState<Skill | null>(null);
  const [panel, setPanel] = useState<DrawerPanel>('basic');
  const [dirty, setDirty] = useState(false);
  const [notice, setNotice] = useState('');

  useEffect(() => {
    if (!skill) return;
    setDraft(skill);
    setDirty(false);
  }, [skill]);

  if (location.pathname.endsWith('/edit')) {
    return <Navigate to={`/admin/tools/${id}?edit=1`} replace />;
  }

  if (isLoading || (skill && !draft)) {
    return (
      <div className="mx-auto w-full max-w-[1440px] p-5 pb-16 sm:p-8 xl:px-6">
        <p className="text-sm text-[var(--text-muted)]">加载中…</p>
      </div>
    );
  }

  if (isError || !skill || !draft) return <NotFound />;

  const onChange = (patch: Partial<Skill>) => {
    if (!editing) return;
    setDraft((current) => (current ? { ...current, ...patch } : current));
    setDirty(true);
  };

  const exitEditing = () => {
    const next = new URLSearchParams(params);
    next.delete('edit');
    setSearchParams(next, { replace: true });
  };

  const toggleEditing = () => {
    if (!editing) {
      setSearchParams({ edit: '1' });
      return;
    }
    if (!dirty || !draft) {
      if (skill) {
        setDraft(skill);
        setDirty(false);
      }
      exitEditing();
      return;
    }
    update.mutate({
      id: draft.id,
      patch: {
        name: draft.name,
        description: draft.description,
        owner: draft.owner,
        version: draft.version,
        type: draft.type,
        status: draft.status,
        risk: draft.risk,
        needConfirm: draft.needConfirm,
        visibleScope: draft.visibleScope,
        tags: draft.tags,
        starred: draft.starred,
        inputSchema: draft.inputSchema,
        outputSchema: draft.outputSchema,
        runtime: draft.runtime,
      },
    }, {
      onSuccess: () => {
        setDirty(false);
        setNotice(`已保存「${draft.name}」。`);
        exitEditing();
      },
    });
  };

  return (
    <SkillWorkspace
      skill={draft}
      editing={editing}
      panel={panel}
      setPanel={setPanel}
      onChange={onChange}
      onToggleEditing={toggleEditing}
      notice={notice}
      onCloseNotice={() => setNotice('')}
      saving={update.isPending}
    />
  );
}
