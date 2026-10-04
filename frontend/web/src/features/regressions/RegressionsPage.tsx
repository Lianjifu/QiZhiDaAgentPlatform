/**
 * AdminRegressions — orchestrator。
 * 对齐技能管理：无子模块 Tab，Hero 轻量，列表工具栏承载导入/新建。
 * 追踪 / 告警 / 时间线 走 useApiQuery 拉取;写操作(CRUD/批量/导入导出/告警)走本地乐观更新。
 */
import { Plus, Search, Upload } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AdminListPagination, paginateItems } from '@/components/feedback/AdminListPagination';
import { AdminListHeader, AdminListHeaderMetrics } from '@/components/feedback/AdminListRow';
import { NoticeBanner } from '@/components/feedback/NoticeBanner';
import { useRegressionAlerts, useRegressionTimeline, useRegressionTracks } from './useRegressions';
import type { AlertRule, ExchangeFormat, RegressionRisk, RegressionTrack } from './schema';
import { RISK_FILTER, STATUS_FILTER, uid } from './components/constants';
import { AlertEditModal, DeleteTrackModal, ExportTrackModal, ImportTrackModal } from './components/Modals';
import { AlertTab, BaselineTab, RiskTab, TimelineTab } from './components/tabs/Tabs';
import { BatchToolbar } from './components/BatchToolbar';
import { TrackCard } from './components/TrackCard';

type ViewId = 'track' | 'baseline' | 'risk' | 'timeline' | 'alert';

const EMPTY_TRACKS: RegressionTrack[] = [];
const EMPTY_ALERTS: AlertRule[] = [];

export default function RegressionsPage() {
  const navigate = useNavigate();
  const remoteTracks = useRegressionTracks();
  const remoteAlerts = useRegressionAlerts();
  const remoteTimeline = useRegressionTimeline();
  const tracksData = remoteTracks.data ?? EMPTY_TRACKS;
  const alertsData = remoteAlerts.data ?? EMPTY_ALERTS;
  const timelineData = remoteTimeline.data ?? [];

  const [tracks, setTracks] = useState<RegressionTrack[]>([]);
  const [alerts, setAlerts] = useState<AlertRule[]>([]);
  const [view, setView] = useState<ViewId>('track');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | RegressionTrack['status']>('all');
  const [riskFilter, setRiskFilter] = useState<'all' | RegressionRisk>('all');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [deleteTarget, setDeleteTarget] = useState<RegressionTrack | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [editingAlert, setEditingAlert] = useState<AlertRule | null>(null);
  const [notice, setNotice] = useState('');
  const [page, setPage] = useState(1);

  useEffect(() => { setTracks(tracksData); }, [remoteTracks.data]);
  useEffect(() => { setAlerts(alertsData); }, [remoteAlerts.data]);

  const counts = useMemo(() => {
    const total = tracks.length;
    const regressed = tracks.filter((t) => t.status === 'regressed').length;
    const investigating = tracks.filter((t) => t.status === 'investigating').length;
    return { total, regressed, investigating };
  }, [tracks]);

  const visibleTracks = useMemo(() => {
    const q = search.trim().toLowerCase();
    return tracks.filter((t) =>
      (statusFilter === 'all' || t.status === statusFilter) &&
      (riskFilter === 'all' || t.risk === riskFilter) &&
      (q.length === 0 || `${t.name} ${t.agent} ${t.owner} ${t.tags.join(' ')}`.toLowerCase().includes(q)),
    );
  }, [tracks, statusFilter, riskFilter, search]);

  useEffect(() => { setPage(1); }, [search, statusFilter, riskFilter, view]);
  const paged = useMemo(() => paginateItems(visibleTracks, page), [visibleTracks, page]);

  const toggleSelect = (id: string) => setSelectedIds((current) => current.includes(id) ? current.filter((x) => x !== id) : [...current, id]);
  const toggleStar = (id: string) => setTracks((current) => current.map((t) => t.id === id ? { ...t, starred: !t.starred } : t));

  const openTrack = (track: RegressionTrack) => {
    navigate(`/admin/regressions/${track.id}`);
  };

  const handleDuplicate = (track: RegressionTrack) => {
    const copy: RegressionTrack = { ...track, id: uid('track'), name: `${track.name} 副本`, starred: false, lastCheckedAt: '未运行', history: [], casesList: [] };
    setTracks((current) => [copy, ...current]);
    setNotice(`已复制追踪:${copy.name}`);
  };

  const handleDelete = (track: RegressionTrack) => {
    setTracks((current) => current.filter((t) => t.id !== track.id));
    setNotice(`已删除「${track.name}」。`);
    setDeleteTarget(null);
  };

  const handleInvestigate = (track: RegressionTrack) => {
    setTracks((current) => current.map((t) => t.id === track.id ? { ...t, status: 'investigating' } : t));
    setNotice(`已标记排查中:${track.name}`);
  };

  const handleResolve = (track: RegressionTrack) => {
    setTracks((current) => current.map((t) => t.id === track.id ? { ...t, status: 'stable' } : t));
    setNotice(`已标记已解决:${track.name}`);
  };

  const handleBatchInvestigate = () => {
    setTracks((current) => current.map((t) => selectedIds.includes(t.id) ? { ...t, status: 'investigating' } : t));
    setNotice(`已批量标记排查中 ${selectedIds.length} 条。`);
    setSelectedIds([]);
  };

  const handleBatchResolve = () => {
    setTracks((current) => current.map((t) => selectedIds.includes(t.id) ? { ...t, status: 'stable' } : t));
    setNotice(`已批量标记已解决 ${selectedIds.length} 条。`);
    setSelectedIds([]);
  };

  const handleBatchDelete = () => {
    setTracks((current) => current.filter((t) => !selectedIds.includes(t.id)));
    setNotice(`已批量删除 ${selectedIds.length} 条。`);
    setSelectedIds([]);
  };

  const handleCreate = (track: RegressionTrack) => {
    setTracks((current) => [track, ...current]);
    setNotice(`已创建回归追踪「${track.name}」。`);
    setView('track');
  };

  const handleImport = (count: number) => {
    for (let i = 0; i < count; i += 1) {
      const newTrack: RegressionTrack = {
        id: uid('track'),
        name: `导入追踪 ${i + 1}`,
        agent: '待指定', owner: '张敏',
        status: 'stable', risk: 'low',
        baselineVersion: 'v1.0', currentVersion: 'v1.0',
        passRateDelta: 0, latencyDelta: 0, costDelta: 0, scoreDelta: 0,
        baseline: { passRate: 95, avgScore: 4.4, latencyMs: 1200, cost: 10 },
        current: { passRate: 95, avgScore: 4.4, latencyMs: 1200, cost: 10 },
        passRateTrend: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        latencyTrend: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        costTrend: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        lastCheckedAt: '未运行', cases: 0, starred: false,
        schedule: '每次发布后', tags: [], notes: '从外部文件导入',
        history: [], casesList: [],
      };
      setTracks((current) => [newTrack, ...current]);
    }
    setNotice(`已导入 ${count} 条追踪。`);
  };

  const handleExport = (format: ExchangeFormat) => {
    const list = selectedIds.length > 0 ? tracks.filter((t) => selectedIds.includes(t.id)) : tracks;
    const payload = list.map((t) => ({ id: t.id, name: t.name, agent: t.agent, baselineVersion: t.baselineVersion, currentVersion: t.currentVersion, status: t.status }));
    if (typeof window === 'undefined' || typeof document === 'undefined') return;
    if (format === 'json') {
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
      downloadBlob(blob, 'regression-tracks.json');
    } else {
      const yaml = payload.map((p) => `- id: "${p.id}"\n  name: "${p.name}"\n  agent: "${p.agent}"\n  baseline: "${p.baselineVersion}"\n  current: "${p.currentVersion}"`).join('\n');
      const blob = new Blob([`${yaml}\n`], { type: 'text/yaml' });
      downloadBlob(blob, 'regression-tracks.yaml');
    }
    setNotice(`已导出 ${list.length} 条追踪为 ${format.toUpperCase()} 文件。`);
  };

  const handleAlertSave = (rule: AlertRule) => {
    setAlerts((current) => current.map((a) => a.id === rule.id ? { ...rule } : a));
    setNotice(`已保存告警规则「${rule.name}」。`);
    setEditingAlert(null);
  };

  const handleAlertToggle = (id: string) => {
    const target = alerts.find((x) => x.id === id);
    setAlerts((current) => current.map((a) => a.id === id ? { ...a, enabled: !a.enabled } : a));
    if (target) setNotice(`已${target.enabled ? '停用' : '启用'}规则「${target.name}」`);
  };

  const handleAlertDelete = (id: string) => {
    const target = alerts.find((x) => x.id === id);
    setAlerts((current) => current.filter((x) => x.id !== id));
    if (target) setNotice(`已删除规则「${target.name}」`);
  };

  const viewSelect = (
    <select
      aria-label="视图"
      value={view}
      onChange={(e) => setView(e.target.value as ViewId)}
      className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-xs outline-none focus:border-[var(--brand)]"
    >
      <option value="track">追踪列表</option>
      <option value="baseline">基线对比</option>
      <option value="risk">风险面板</option>
      <option value="timeline">时间线</option>
      <option value="alert">告警规则</option>
    </select>
  );

  return (
    <div className="regressions-page mx-auto w-full max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-10">
      <section className="relative overflow-hidden rounded-[28px] border border-[var(--border)] bg-[var(--surface-1)] px-6 py-8 shadow-[var(--shadow-sm)] sm:px-8">
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden rounded-[28px]">
          <div className="absolute right-0 top-0 h-full w-1/2 bg-[radial-gradient(circle_at_top_right,rgba(99,102,241,0.10),transparent_68%)]" />
        </div>
        <div className="relative">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-indigo-700 dark:text-indigo-300">ADMIN / 回归追踪</p>
          <h2 className="mt-3 text-2xl font-semibold tracking-tight sm:text-3xl xl:text-4xl">对比基线，发现版本退化。</h2>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-[var(--text-muted)]">{counts.total} 个追踪 · {counts.regressed} 已退化 · {counts.investigating} 排查中。</p>
        </div>
      </section>

      {notice && (
        <NoticeBanner tone="violet" onClose={() => setNotice('')}>
          {notice}
        </NoticeBanner>
      )}

      {selectedIds.length > 0 && view === 'track' && (
        <BatchToolbar
          count={selectedIds.length}
          onClear={() => setSelectedIds([])}
          onBatchInvestigate={handleBatchInvestigate}
          onBatchResolve={handleBatchResolve}
          onBatchDelete={handleBatchDelete}
        />
      )}

      {view === 'track' && (
        <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
          <div className="flex flex-col gap-2 border-b border-[var(--border)] px-4 py-3 sm:flex-row sm:items-center sm:px-5">
            <label className="relative min-w-0 flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-muted)]" />
              <input
                aria-label="搜索追踪"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="搜索追踪 / 标签"
                className="h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] pl-8 pr-3 text-sm outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--brand)]"
              />
            </label>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              {viewSelect}
              <select
                aria-label="状态"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as 'all' | RegressionTrack['status'])}
                className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-xs outline-none focus:border-[var(--brand)]"
              >
                {STATUS_FILTER.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
              </select>
              <select
                aria-label="风险"
                value={riskFilter}
                onChange={(e) => setRiskFilter(e.target.value as 'all' | RegressionRisk)}
                className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-xs outline-none focus:border-[var(--brand)]"
              >
                {RISK_FILTER.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
              </select>
              <button type="button" onClick={() => setImportOpen(true)} className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-3 text-xs font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]">
                <Upload className="h-3.5 w-3.5" />导入
              </button>
              <button type="button" onClick={() => navigate('/admin/regressions/new')} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]">
                <Plus className="h-3.5 w-3.5" />新建追踪
              </button>
            </div>
          </div>
          <AdminListHeader metrics={<AdminListHeaderMetrics labels={['通过率', '延迟', '检查时间']} />} />
          <div className="divide-y divide-[var(--border)]">
            {paged.slice.map((track) => (
              <TrackCard
                key={track.id}
                track={track}
                selected={selectedIds.includes(track.id)}
                onToggleSelect={toggleSelect}
                onSelect={openTrack}
                onToggleStar={toggleStar}
                onDuplicate={handleDuplicate}
                onRequestDelete={setDeleteTarget}
                onInvestigate={handleInvestigate}
                onResolve={handleResolve}
              />
            ))}
          </div>
          <AdminListPagination
            page={paged.safePage}
            totalPages={paged.totalPages}
            total={paged.total}
            pageStart={paged.pageStart}
            pageEnd={paged.pageEnd}
            onPageChange={setPage}
          />
          {visibleTracks.length === 0 && (
            <div className="px-5 pb-8 text-center">
              <Search className="mx-auto h-6 w-6 text-[var(--text-muted)]" />
              <p className="mt-3 text-sm font-semibold">没有匹配的追踪</p>
              <p className="mt-1 text-xs text-[var(--text-muted)]">尝试其他关键词或清除筛选。</p>
            </div>
          )}
        </div>
      )}

      {view !== 'track' && (
        <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
          <div className="flex flex-wrap items-center gap-2 border-b border-[var(--border)] px-4 py-3 sm:px-5">
            {viewSelect}
          </div>
          {view === 'baseline' && <BaselineTab tracks={tracks} />}
          {view === 'risk' && <RiskTab tracks={tracks} />}
          {view === 'timeline' && <TimelineTab events={timelineData} />}
          {view === 'alert' && (
            <AlertTab
              alerts={alerts}
              onToggle={handleAlertToggle}
              onDelete={handleAlertDelete}
              onEdit={setEditingAlert}
            />
          )}
        </div>
      )}

      <DeleteTrackModal open={deleteTarget !== null} onClose={() => setDeleteTarget(null)} onConfirm={() => deleteTarget && handleDelete(deleteTarget)} track={deleteTarget} />
      <ImportTrackModal open={importOpen} onClose={() => setImportOpen(false)} onImport={handleImport} />
      <ExportTrackModal open={exportOpen} onClose={() => setExportOpen(false)} onExport={handleExport} total={tracks.length} selectedCount={selectedIds.length} />
      <AlertEditModal open={editingAlert !== null} onClose={() => setEditingAlert(null)} onSave={handleAlertSave} rule={editingAlert} />
    </div>
  );
}

function downloadBlob(blob: Blob, filename: string) {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
