import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { NoticeBanner } from '@/components/feedback/NoticeBanner';
import {
  useAdminSkills, useUpdateSkill, useDeleteSkill, useBulkPublish, useCreateSkill,
} from './useAdminSkills';
import { normalizeError } from '@/api/shared/http-error';
import type {
  AdminSkillFilters, Skill, SkillExportField, SkillExportFormat, SkillType,
} from './schema';
import { BatchToolbar } from './components/BatchToolbar';
import { DeleteConfirmModal } from './components/DeleteConfirmModal';
import { ImportSkillModal, ExportSkillModal } from './components/ImportExportModals';
import { OverviewPanel } from './components/OverviewPanel';
import { getLifecycleCounts } from './components/constants';
import {
  buildSkillFromDraft, triggerDownload,
  type ImportRow,
} from './components/skill-io';
import { DEFAULT_EXCHANGE_FIELDS } from './components/constants';

const EMPTY_FILTERS: AdminSkillFilters = { type: 'all', status: 'all', q: '', sort: 'updated' };

export default function SkillsPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [filters, setFilters] = useState<AdminSkillFilters>(EMPTY_FILTERS);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [ioType, setIoType] = useState<SkillType>('Skill');
  const [importOpen, setImportOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Skill | null>(null);
  const [notice, setNotice] = useState('');
  const { data: remoteSkills = [], isLoading, isError, error } = useAdminSkills(filters);
  const skills = remoteSkills;
  const update = useUpdateSkill();
  const create = useCreateSkill();
  const created = (location.state as { created?: Skill } | null)?.created;

  useEffect(() => {
    if (!created || isLoading) return;
    setNotice(`已新增技能「${created.name}」,状态为草稿。`);
    navigate('/admin/tools', { replace: true, state: null });
  }, [created, isLoading, navigate, remoteSkills]);
  const del = useDeleteSkill();
  const bulk = useBulkPublish();

  const visible = useMemo(() => {
    const q = (filters.q ?? '').trim().toLowerCase();
    const list = skills.filter((s) =>
      (filters.type === 'all' || filters.type === undefined || s.type === filters.type) &&
      (filters.status === 'all' || filters.status === undefined || s.status === filters.status) &&
      (q.length === 0 || `${s.name} ${s.description} ${s.owner} ${s.tags.join(' ')}`.toLowerCase().includes(q)),
    );
    const sorted = [...list].sort((a, b) => {
      if (filters.sort === 'calls') return b.calls - a.calls;
      if (filters.sort === 'name') return a.name.localeCompare(b.name, 'zh');
      return 0;
    });
    return sorted;
  }, [skills, filters]);

  const counts = useMemo(() => getLifecycleCounts(skills), [skills]);

  const scopedType: SkillType | null = filters.type && filters.type !== 'all' ? filters.type : null;
  const createLabel = scopedType === 'Tool' ? '新建 Tool' : scopedType === 'MCP' ? '新建 MCP' : '新建技能';

  const toggleSelect = (id: string) => {
    setSelectedIds((current) => current.includes(id) ? current.filter((x) => x !== id) : [...current, id]);
  };
  const openSkill = (skill: Skill) => {
    navigate(`/admin/tools/${skill.id}`);
  };
  const openEdit = (skill: Skill) => {
    navigate(`/admin/tools/${skill.id}?edit=1`);
  };

  const toggleStar = (id: string) => {
    const skill = skills.find((item) => item.id === id);
    if (!skill) return;
    update.mutate({ id, patch: { starred: !skill.starred } }, {
      onSuccess: () => setNotice(`已更新「${skill.name}」收藏状态。`),
      onError: (cause) => setNotice(`更新失败：${normalizeError(cause).message}`),
    });
  };

  const handlePublish = (skill: Skill) => {
    if (skill.status === 'published') return;
    update.mutate({ id: skill.id, patch: { status: 'published' } }, {
      onSuccess: () => setNotice(`已发布「${skill.name}」。`),
      onError: (cause) => setNotice(`发布失败：${normalizeError(cause).message}`),
    });
  };

  const handleDelete = (skill: Skill) => {
    del.mutate({ id: skill.id }, {
      onSuccess: () => { setNotice(`已删除「${skill.name}」。`); setDeleteTarget(null); },
      onError: (cause) => setNotice(`删除失败：${normalizeError(cause).message}`),
    });
  };

  const handleBatchDelete = () => {
    if (selectedIds.length === 0) return;
    const removedIds = [...selectedIds];
    Promise.all(removedIds.map((id) => del.mutateAsync({ id }))).then(() => {
      setNotice(`已批量删除 ${removedIds.length} 个技能。`);
      setSelectedIds([]);
    }).catch((cause) => setNotice(`批量删除失败：${normalizeError(cause).message}`));
  };
  const handleBatchPublish = () => {
    if (selectedIds.length === 0) return;
    const ids = [...selectedIds];
    bulk.mutate({ ids, action: 'publish' }, {
      onSuccess: () => { setNotice(`已批量发布 ${ids.length} 个技能。`); setSelectedIds([]); },
      onError: (cause) => setNotice(`批量发布失败：${normalizeError(cause).message}`),
    });
  };
  const handleBatchExport = () => setExportOpen(true);

  const openCreate = () => {
    navigate(scopedType ? `/admin/tools/new?type=${scopedType}` : '/admin/tools/new');
  };

  const openImport = () => {
    setIoType(scopedType ?? 'Skill');
    setImportOpen(true);
  };
  const handleImport = (rows: ImportRow[]) => {
    const okRows = rows.filter((r) => r.status === 'ok');
    const newSkills: Skill[] = okRows.map((row) => buildSkillFromDraft(row.name, ioType, '', '张敏', 'low'));
    Promise.all(newSkills.map((skill) => create.mutateAsync({
      id: skill.id, name: skill.name, type: skill.type, description: skill.description,
      owner: skill.owner, risk: skill.risk, needConfirm: skill.needConfirm,
      inputSchema: skill.inputSchema, outputSchema: skill.outputSchema,
      profile: skill.profile, runtime: skill.runtime,
    }))).then(() => setNotice(`已导入 ${okRows.length} 个 ${ioType}(其余已跳过)。`))
      .catch((cause) => setNotice(`导入失败：${normalizeError(cause).message}`));
  };

  const handleExportOne = (skill: Skill) => {
    triggerDownload([skill], 'json', DEFAULT_EXCHANGE_FIELDS, `skill-${skill.name}`);
    setNotice(`已导出「${skill.name}」。`);
  };

  const handleExport = (format: SkillExportFormat, fields: Record<SkillExportField, boolean>) => {
    const pool = scopedType ? skills.filter((s) => s.type === scopedType) : skills;
    const picked = selectedIds.length > 0 ? pool.filter((s) => selectedIds.includes(s.id)) : pool;
    const list = picked.length > 0 ? picked : pool;
    const label = scopedType ?? '全部';
    triggerDownload(list, format, fields, `${(scopedType ?? 'all').toLowerCase()}-skills-export`);
    setNotice(`已导出 ${list.length} 个 ${label} 为 ${format.toUpperCase()} 文件。`);
  };

  return (
    <div className="skills-page mx-auto w-full max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-10">
      <section className="relative overflow-hidden rounded-[28px] border border-[var(--border)] bg-[var(--surface-1)] px-6 py-8 shadow-[var(--shadow-sm)] sm:px-8">
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden rounded-[28px]">
          <div className="absolute right-0 top-0 h-full w-1/2 bg-[radial-gradient(circle_at_top_right,rgba(139,92,246,0.10),transparent_68%)]" />
        </div>
        <div className="relative">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-violet-700 dark:text-violet-300">ADMIN / 技能管理</p>
          <h2 className="mt-3 text-2xl font-semibold tracking-tight sm:text-3xl xl:text-4xl">维护智能体可调用的技能。</h2>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-[var(--text-muted)]">{skills.length} 个技能 · 已发布 {counts.published}。</p>
        </div>
      </section>

      {notice && (
        <NoticeBanner tone="violet" onClose={() => setNotice('')}>
          {notice}
        </NoticeBanner>
      )}
      {isError && (
        <NoticeBanner tone="rose" onClose={() => undefined}>
          加载失败：{normalizeError(error).message}
        </NoticeBanner>
      )}

      {selectedIds.length > 0 && (
        <BatchToolbar
          count={selectedIds.length}
          onClear={() => setSelectedIds([])}
          onBatchPublish={handleBatchPublish}
          onBatchDelete={handleBatchDelete}
          onBatchExport={handleBatchExport}
        />
      )}
      <OverviewPanel
        visible={visible}
        filters={filters}
        onFiltersChange={setFilters}
        selectedIds={selectedIds}
        onToggleSelect={toggleSelect}
        onToggleStar={toggleStar}
        onSelect={openSkill}
        onEdit={openEdit}
        onPublish={handlePublish}
        onExportOne={handleExportOne}
        onRequestDelete={setDeleteTarget}
        createLabel={createLabel}
        onCreate={openCreate}
        onImport={openImport}
      />
      {isLoading && !skills.length && <p className="text-xs text-[var(--text-muted)]">加载中…</p>}

      <ImportSkillModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImport={handleImport}
        existing={skills}
      />

      <ExportSkillModal
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        onExport={handleExport}
        total={(scopedType ? skills.filter((s) => s.type === scopedType) : skills).length}
        selectedCount={(scopedType ? skills.filter((s) => s.type === scopedType) : skills).filter((s) => selectedIds.includes(s.id)).length}
      />

      <DeleteConfirmModal
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget && handleDelete(deleteTarget)}
        skill={deleteTarget}
      />
    </div>
  );
}
