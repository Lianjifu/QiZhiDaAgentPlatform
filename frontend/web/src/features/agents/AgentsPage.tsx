/**
 * 管理侧「智能体工作台」主面板 — Hero + Tab + 筛选 + 卡片网格(分页)+ 批量工具栏 + 向导/导入/导出/删除。
 *
 * 详情查看已迁移到独立路由 /admin/agents/:id (AgentDetailPage),
 * 这里只负责列表 + 批量操作,不再内嵌 Drawer。
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, ChevronLeft, ChevronRight, Plus, Search, Star, Upload } from 'lucide-react';
import type {
  AgentEntry, AgentFilters, ImportExtension, ImportRow, ExportField, ExportFormat, ExportScope, SortKey, TabId,
} from './schema';
import type { DeletePayload } from './components/DeleteConfirmModal';
import {
  useAgentsList, useBatchSetStatus, useDeleteAgents, useExportAgents, useImportAgents, useToggleStar,
} from './useAgents';
import { AgentCard } from './components/AgentCard';
import { BatchToolbar } from './components/DrawerSidebar';
import { DeleteConfirmModal } from './components/DeleteConfirmModal';
import { ExportDialog, ImportDialog } from './components/ImportExportModals';
import { TABS, DEFAULT_EXPORT_FIELDS } from './components/constants';

const PAGE_SIZE = 4;

export default function AgentsPage() {
  const navigate = useNavigate();
  const [filters, setFilters] = useState<AgentFilters>({ tab: 'all', sortKey: 'calls', search: '', scene: '全部场景' });
  const { data: list = [], isLoading } = useAgentsList(filters);
  const deleteAgents = useDeleteAgents();
  const batchStatus = useBatchSetStatus();
  const toggleStar = useToggleStar();
  const importAgents = useImportAgents();
  const exportAgents = useExportAgents();

  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const [importOpen, setImportOpen] = useState(false);
  const [importStep, setImportStep] = useState<1 | 2 | 3>(1);
  const [importFileName, setImportFileName] = useState('');
  const [importExtension, setImportExtension] = useState<ImportExtension>('json');
  const [importPreview, setImportPreview] = useState<ImportRow[]>([]);

  const [exportOpen, setExportOpen] = useState(false);
  const [exportScope, setExportScope] = useState<ExportScope>('all');
  const [exportFormat, setExportFormat] = useState<ExportFormat>('json');
  const [exportFields, setExportFields] = useState<Record<ExportField, boolean>>(DEFAULT_EXPORT_FIELDS);

  const [deletePayload, setDeletePayload] = useState<DeletePayload | null>(null);

  const [page, setPage] = useState(1);

  const filteredList = useMemo(() => {
    const search = (filters.search ?? '').trim().toLowerCase();
    const scene = filters.scene ?? '全部场景';
    const tab = filters.tab ?? 'all';
    return list.filter((agent) => {
      if (tab !== 'all' && agent.status !== tab) return false;
      if (scene !== '全部场景' && !agent.category.startsWith(scene)) return false;
      if (search.length > 0 && !`${agent.name}${agent.description}${agent.category}${agent.owner}`.toLowerCase().includes(search)) return false;
      return true;
    }).sort((a, b) => {
      const sortKey: SortKey = filters.sortKey ?? 'calls';
      switch (sortKey) {
        case 'calls': return b.calls - a.calls;
        case 'rating': return b.rating - a.rating;
        case 'name': return a.name.localeCompare(b.name, 'zh-Hans-CN');
        case 'updated':
        default: return 0;
      }
    });
  }, [list, filters]);

  const totalPages = Math.max(1, Math.ceil(filteredList.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pagedList = useMemo(
    () => filteredList.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE),
    [filteredList, safePage],
  );
  const pageStart = filteredList.length === 0 ? 0 : (safePage - 1) * PAGE_SIZE + 1;
  const pageEnd = Math.min(safePage * PAGE_SIZE, filteredList.length);

  useEffect(() => {
    setPage(1);
  }, [filters]);

  const handleToggleSelect = (id: string) => {
    setSelectedIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
  };
  const handleClearSelection = () => setSelectedIds([]);

  const handleBatchPublish = () => batchStatus.mutate({ ids: selectedIds, status: 'published' });
  const handleBatchRetire = () => batchStatus.mutate({ ids: selectedIds, status: 'retired' });
  const handleBatchDelete = () => setDeletePayload({ kind: 'bulk', agentNames: selectedIds.map((id) => list.find((a) => a.id === id)?.name ?? id) });

  const handleToggleStar = (id: string) => {
    const agent = list.find((a) => a.id === id);
    if (!agent) return;
    toggleStar.mutate({ id, starred: !agent.starred });
  };

  const handleOpenDetail = (agent: AgentEntry) => {
    navigate(`/admin/agents/${agent.id}`);
  };
  const handleOpenEdit = (agent: AgentEntry) => {
    navigate(`/admin/agents/${agent.id}?edit=1`);
  };

  const handlePublish = (agent: AgentEntry) => {
    if (agent.status === 'published') return;
    batchStatus.mutate({ ids: [agent.id], status: 'published' });
  };
  const handleExportOne = (agent: AgentEntry) => {
    setSelectedIds([agent.id]);
    setExportScope('selected');
    setExportOpen(true);
  };
  const handleRequestDelete = (agent: AgentEntry) => setDeletePayload({ kind: 'single', agentName: agent.name });

  const handleOpenCreate = () => navigate('/admin/agents/new');

  const handleConfirmDelete = () => {
    if (!deletePayload) return;
    const ids = deletePayload.kind === 'single'
      ? list.filter((a) => a.name === deletePayload.agentName).map((a) => a.id)
      : selectedIds;
    deleteAgents.mutate({ ids }, { onSuccess: () => { setDeletePayload(null); setSelectedIds([]); } });
  };

  const handleImportFile = async (file: File) => {
    const ext = file.name.split('.').pop()?.toLowerCase() as ImportExtension ?? 'json';
    setImportFileName(file.name);
    setImportExtension(ext);
    try {
      if (ext !== 'json') throw new Error('当前仅支持 JSON 文件解析');
      const parsed: unknown = JSON.parse(await file.text());
      const records = Array.isArray(parsed) ? parsed : [parsed];
      const rows: ImportRow[] = records.map((record) => {
        if (!record || typeof record !== 'object') throw new Error('导入条目必须是对象');
        const source = record as Partial<AgentEntry>;
        if (!source.name) throw new Error('缺少智能体名称');
        return { name: source.name, category: source.category ?? '', owner: source.owner ?? '', status: 'ok', source: record as Record<string, unknown> };
      });
      setImportPreview(rows);
    } catch (error) { setImportPreview([]); window.alert(`导入失败：${String(error)}`); return; }
    setImportStep(2);
  };
  const handleConfirmImport = (force: boolean) => {
    importAgents.mutate({ rows: importPreview, force }, { onSuccess: () => { setImportOpen(false); setImportStep(1); setImportPreview([]); setImportFileName(''); } });
  };

  const handleConfirmExport = () => {
    const enabledFields = (Object.keys(exportFields) as ExportField[]).filter((k) => exportFields[k]);
    exportAgents.mutate({
      scope: exportScope,
      format: 'json',
      fields: enabledFields,
      ids: exportScope === 'selected' ? selectedIds : exportScope === 'tab' ? filteredList.map((agent) => agent.id) : undefined,
    }, { onSuccess: (result) => {
      if (!Array.isArray(result)) { window.alert('后端返回的导出格式无效。'); return; }
      const payload = JSON.stringify(result, null, 2);
      const link = document.createElement('a');
      link.href = URL.createObjectURL(new Blob([payload], { type: 'application/json' }));
      link.download = 'agents.json';
      link.click();
      URL.revokeObjectURL(link.href);
      setExportOpen(false);
    } });
  };

  const countsForExport = { all: list.length, tab: filteredList.length, selected: selectedIds.length };

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-6">
      {/* Hero */}
      <section className="relative overflow-hidden rounded-[28px] border border-[var(--border)] bg-[var(--surface-1)] px-6 py-8 shadow-[var(--shadow-sm)] sm:px-8">
        <div aria-hidden="true" className="pointer-events-none absolute right-0 top-0 h-full w-1/2 bg-[radial-gradient(circle_at_top_right,var(--brand-light),transparent_68%)]" />
        <div className="relative">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--brand)]">ADMIN / 智能体管理</p>
          <h1 className="mt-3 text-2xl font-semibold tracking-tight sm:text-3xl xl:text-4xl">配置、审核并发布智能体。</h1>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-[var(--text-muted)]">{list.length} 个智能体 · {list.filter((a) => a.status === 'published').length} 已发布。</p>
        </div>
      </section>

      {/* Batch Toolbar */}
      {selectedIds.length > 0 && (
        <BatchToolbar
          count={selectedIds.length}
          onClear={handleClearSelection}
          onBatchPublish={handleBatchPublish}
          onBatchRetire={handleBatchRetire}
          onBatchDelete={handleBatchDelete}
          onBatchExport={() => { setExportScope('selected'); setExportOpen(true); }}
        />
      )}

      <section aria-label="智能体列表" className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
        <div className="flex flex-col gap-2 border-b border-[var(--border)] px-4 py-3 sm:flex-row sm:items-center sm:px-5">
          <label className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-muted)]" />
            <input
              type="text"
              aria-label="搜索智能体"
              placeholder="搜索名称、描述、负责人"
              value={filters.search ?? ''}
              onChange={(event) => setFilters((f) => ({ ...f, search: event.target.value }))}
              className="h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] pl-8 pr-3 text-sm outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--brand)]"
            />
          </label>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <select
              aria-label="状态"
              value={filters.tab ?? 'all'}
              onChange={(event) => setFilters((f) => ({ ...f, tab: event.target.value as TabId }))}
              className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-xs outline-none focus:border-[var(--brand)]"
            >
              {TABS.map((tab) => (
                <option key={tab.id} value={tab.id}>{tab.id === 'all' ? '全部状态' : tab.label}</option>
              ))}
            </select>
            <div role="group" aria-label="列表操作" className="flex items-center gap-2">
              <button type="button" onClick={() => { setImportOpen(true); setImportStep(1); setImportPreview([]); setImportFileName(''); }} className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-3 text-xs font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]">
                <Upload className="h-3.5 w-3.5" />导入
              </button>
              <button type="button" onClick={handleOpenCreate} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]">
                <Plus className="h-3.5 w-3.5" />新建智能体
              </button>
            </div>
          </div>
        </div>
        <div className="space-y-3 p-5">

        {pagedList.length > 0 ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {pagedList.map((agent) => (
              <AgentCard
                key={agent.id}
                agent={agent}
                onSelect={handleOpenDetail}
                onToggleStar={handleToggleStar}
                selected={selectedIds.includes(agent.id)}
                onToggleSelect={handleToggleSelect}
                onEdit={handleOpenEdit}
                onPublish={handlePublish}
                onExportOne={handleExportOne}
                onRequestDelete={handleRequestDelete}
              />
            ))}
          </div>
        ) : (
          <div className="rounded-2xl border border-dashed border-[var(--border)] bg-[var(--surface-1)] p-8 text-center">
            <AlertTriangle className="mx-auto h-6 w-6 text-[var(--warning)]" />
            <p className="mt-3 text-sm font-semibold">没有匹配的智能体</p>
            <p className="mt-1 text-xs text-[var(--text-muted)]">尝试调整筛选,或新建一个智能体。</p>
          </div>
        )}

        {totalPages > 1 && (
          <nav aria-label="分页" className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] px-4 py-2.5 text-xs">
            <span className="text-[var(--text-muted)]">
              第 <span className="font-semibold tabular-nums text-[var(--text)]">{pageStart}-{pageEnd}</span> 个 / 共 <span className="font-semibold tabular-nums text-[var(--text)]">{filteredList.length}</span> 个
            </span>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={safePage <= 1}
                aria-label="上一页"
                className="inline-flex items-center gap-1 rounded-lg border border-[var(--border)] px-2.5 py-1 text-[11px] font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)] disabled:cursor-not-allowed disabled:opacity-40"
              >
                <ChevronLeft className="h-3 w-3" />上一页
              </button>
              {Array.from({ length: totalPages }, (_, i) => i + 1).map((n) => {
                const active = n === safePage;
                return (
                  <button
                    key={n}
                    type="button"
                    onClick={() => setPage(n)}
                    aria-current={active ? 'page' : undefined}
                    aria-label={`第 ${n} 页`}
                    className={`grid h-7 w-7 place-items-center rounded-lg text-[11px] font-semibold transition ${active ? 'bg-[var(--brand)] text-white' : 'border border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]'}`}
                  >
                    {n}
                  </button>
                );
              })}
              <button
                type="button"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={safePage >= totalPages}
                aria-label="下一页"
                className="inline-flex items-center gap-1 rounded-lg border border-[var(--border)] px-2.5 py-1 text-[11px] font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)] disabled:cursor-not-allowed disabled:opacity-40"
              >
                下一页<ChevronRight className="h-3 w-3" />
              </button>
            </div>
          </nav>
        )}
        </div>
      </section>

      {/* Import Dialog */}
      <ImportDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        step={importStep}
        setStep={setImportStep}
        fileName={importFileName}
        preview={importPreview}
        extension={importExtension}
        onImportFile={handleImportFile}
        onConfirm={handleConfirmImport}
      />

      {/* Export Dialog */}
      <ExportDialog
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        scope={exportScope}
        setScope={setExportScope}
        format={exportFormat}
        setFormat={setExportFormat}
        fields={exportFields}
        setFields={setExportFields}
        counts={countsForExport}
        onConfirm={handleConfirmExport}
      />

      {/* Delete Confirm */}
      <DeleteConfirmModal
        open={deletePayload !== null}
        payload={deletePayload}
        onClose={() => setDeletePayload(null)}
        onConfirm={handleConfirmDelete}
      />
    </div>
  );
}

export { Star };
