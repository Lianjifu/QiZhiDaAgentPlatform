import { useServerAction } from '@/services/useServerAction';
/**
 * NotificationsPage — 对齐模型管理：无子模块 Tab，Hero 轻量，列表工具栏承载导入/新建。
 * 视图筛选：渠道列表 / Webhook / 接收人组；渠道视图可按类型筛选。
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Globe, Plus, Search, Upload } from 'lucide-react';
import { AdminListPagination, paginateItems } from '@/components/feedback/AdminListPagination';
import { AdminListHeader, AdminListHeaderMetrics } from '@/components/feedback/AdminListRow';
import { NoticeBanner } from '@/components/feedback/NoticeBanner';
import {
  useBatchChannelStatus, useCreateGroup,
  useNotificationChannels, useNotificationGroups, useNotificationWebhooks, useUpdateChannel,
} from './useNotifications';
import type { NotificationChannel, NotificationGroup } from './schema';
import { BatchToolbar } from './components/BatchToolbar';
import { ChannelCard } from './components/ChannelCard';
import { CreateGroupModal } from './components/CreateGroupModal';
import { ExportChannelModal } from './components/ExportChannelModal';
import { GroupCard } from './components/GroupCard';
import { ImportChannelModal } from './components/ImportChannelModal';
import { WebhookCard } from './components/WebhookCard';
import { KIND_META, type ExchangeFormat } from './components/constants';

type ViewId = 'channel' | 'webhook' | 'group';
type KindFilter = 'all' | 'feishu' | 'wecom' | 'dingtalk' | 'web';

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

export default function NotificationsPage() {
  const navigate = useNavigate();
  const { data: channels = [] } = useNotificationChannels();
  const { data: webhooks = [] } = useNotificationWebhooks();
  const { data: groups = [] } = useNotificationGroups();

  const updateChannel = useUpdateChannel();
  const batchStatus = useBatchChannelStatus();
  const createGroup = useCreateGroup();

  const [view, setView] = useState<ViewId>('channel');
  const [kindFilter, setKindFilter] = useState<KindFilter>('all');
  const [search, setSearch] = useState('');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [createGroupOpen, setCreateGroupOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [notice, setNotice] = useState('');
  const server = useServerAction(setNotice);
  const [page, setPage] = useState(1);

  const stats = useMemo(() => {
    const total = channels.length;
    const active = channels.filter((c) => c.status === 'active').length;
    const sentToday = channels.reduce((s, c) => s + c.sentToday, 0);
    return { total, active, sentToday };
  }, [channels]);

  const visibleChannels = useMemo(() => {
    const q = search.trim().toLowerCase();
    return channels.filter((c) =>
      (kindFilter === 'all' || c.kind === kindFilter) &&
      (q.length === 0 || `${c.name} ${c.target} ${c.description} ${KIND_META[c.kind].label}`.toLowerCase().includes(q)),
    );
  }, [channels, search, kindFilter]);

  useEffect(() => { setPage(1); }, [search, kindFilter, view]);
  const paged = useMemo(() => paginateItems(visibleChannels, page), [visibleChannels, page]);

  const toggleSelect = (id: string) =>
    setSelectedIds((current) => current.includes(id) ? current.filter((x) => x !== id) : [...current, id]);

  const openChannel = (c: NotificationChannel) => navigate(`/admin/notifications/${c.id}`);

  const handleEnable = (c: NotificationChannel) => {
    if (c.status === 'active') return;
    updateChannel.mutate({ id: c.id, patch: { status: 'active' } }, { onSuccess: () => setNotice(`已启用渠道「${c.name}」。`) });
  };

  const handleExportOne = (c: NotificationChannel) => {
    downloadBlob(new Blob([JSON.stringify(c, null, 2)], { type: 'application/json' }), `channel-${c.id}.json`);
    setNotice(`已导出「${c.name}」。`);
  };

  const handleRequestDelete = (c: NotificationChannel) => {
    setNotice(`渠道「${c.name}」暂不支持删除，可先暂停或导出备份。`);
  };

  const handleBatchEnable = () => {
    batchStatus.mutate({ ids: selectedIds, status: 'active' }, {
      onSuccess: () => { setNotice(`已批量启用 ${selectedIds.length} 个渠道。`); setSelectedIds([]); },
    });
  };
  const handleBatchPause = () => {
    batchStatus.mutate({ ids: selectedIds, status: 'paused' }, {
      onSuccess: () => { setNotice(`已批量暂停 ${selectedIds.length} 个渠道。`); setSelectedIds([]); },
    });
  };
  const handleBatchExport = () => setExportOpen(true);

  const handleCreateGroup = (g: NotificationGroup) => {
    createGroup.mutate(
      { name: g.name, description: g.description, members: g.members },
      {
        onSuccess: (created) => { setNotice(`已创建接收人组「${created.name}」。`); setCreateGroupOpen(false); },
        onError: () => setNotice(`创建失败,请重试。`),
      },
    );
  };

  const handleImport = (_count: number, content: string, format: ExchangeFormat) => server.mutate({ path: '/api/admin/notifications/channels/import', body: { content, format }, success: '已导入', onSuccess: () => setImportOpen(false) });

  const handleExport = (format: ExchangeFormat) => {
    const list = selectedIds.length > 0 ? channels.filter((c) => selectedIds.includes(c.id)) : channels;
    const data = list.map((c) => ({ id: c.id, name: c.name, kind: c.kind, target: c.target, status: c.status }));
    if (format === 'json') {
      downloadBlob(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }), 'channels.json');
    } else {
      const yaml = data.map((c) => `- id: "${c.id}"\n  name: "${c.name}"\n  kind: "${c.kind}"`).join('\n');
      downloadBlob(new Blob([`${yaml}\n`], { type: 'text/yaml' }), 'channels.yaml');
    }
    setNotice(`已导出 ${list.length} 个渠道为 ${format.toUpperCase()} 文件。`);
  };

  const toggleStar = (id: string) => {
    const target = channels.find((c) => c.id === id);
    if (!target) return;
    updateChannel.mutate(
      { id, patch: { starred: !target.starred } },
      { onError: () => setNotice(`更新收藏失败,请重试。`) },
    );
  };

  return (
    <div className="notifications-page mx-auto w-full max-w-[1440px] space-y-6 p-5 pb-16 sm:p-8 xl:px-10">
      <section className="relative overflow-hidden rounded-[28px] border border-[var(--border)] bg-[var(--surface-1)] px-6 py-8 shadow-[var(--shadow-sm)] sm:px-8">
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden rounded-[28px]">
          <div className="absolute right-0 top-0 h-full w-1/2 bg-[radial-gradient(circle_at_top_right,rgba(168,85,247,0.10),transparent_68%)]" />
        </div>
        <div className="relative">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-violet-700 dark:text-violet-300">ADMIN / 渠道配置</p>
          <h2 className="mt-3 text-2xl font-semibold tracking-tight sm:text-3xl xl:text-4xl">接入飞书、企微、钉钉和 Web。</h2>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-[var(--text-muted)]">{stats.total} 个渠道 · {stats.active} 已接入 · 今日会话 {stats.sentToday}。</p>
        </div>
      </section>

      {notice && (
        <NoticeBanner tone="violet" onClose={() => setNotice('')}>
          {notice}
        </NoticeBanner>
      )}

      {selectedIds.length > 0 && view === 'channel' && (
        <BatchToolbar
          count={selectedIds.length}
          onClear={() => setSelectedIds([])}
          onBatchEnable={handleBatchEnable}
          onBatchPause={handleBatchPause}
          onBatchExport={handleBatchExport}
        />
      )}

      {view === 'channel' && (
        <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
          <div className="flex flex-col gap-2 border-b border-[var(--border)] px-4 py-3 sm:flex-row sm:items-center sm:px-5">
            <label className="relative min-w-0 flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-muted)]" />
              <input
                aria-label="搜索渠道"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="搜索渠道 / 平台 / 入口"
                className="h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] pl-8 pr-3 text-sm outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--brand)]"
              />
            </label>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              <select
                aria-label="视图"
                value={view}
                onChange={(e) => setView(e.target.value as ViewId)}
                className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-xs outline-none focus:border-[var(--brand)]"
              >
                <option value="channel">渠道列表</option>
                <option value="webhook">Webhook</option>
                <option value="group">接收人组</option>
              </select>
              <select
                aria-label="类型"
                value={kindFilter}
                onChange={(e) => setKindFilter(e.target.value as KindFilter)}
                className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-xs outline-none focus:border-[var(--brand)]"
              >
                <option value="all">全部平台</option>
                <option value="feishu">飞书</option>
                <option value="wecom">企业微信</option>
                <option value="dingtalk">钉钉</option>
                <option value="web">Web</option>
              </select>
              <button type="button" onClick={() => setImportOpen(true)} className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-3 text-xs font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]">
                <Upload className="h-3.5 w-3.5" />导入
              </button>
              <button type="button" onClick={() => navigate('/admin/notifications/new')} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]">
                <Plus className="h-3.5 w-3.5" />新建渠道
              </button>
            </div>
          </div>
          <AdminListHeader metrics={<AdminListHeaderMetrics labels={['今日会话', '成功率', '最近']} />} />
          <div className="divide-y divide-[var(--border)]">
            {paged.slice.map((c) => (
              <ChannelCard
                key={c.id}
                channel={c}
                selected={selectedIds.includes(c.id)}
                onToggleSelect={toggleSelect}
                onSelect={openChannel}
                onToggleStar={toggleStar}
                onEnable={handleEnable}
                onExportOne={handleExportOne}
                onRequestDelete={handleRequestDelete}
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
          {visibleChannels.length === 0 && (
            <div className="px-5 pb-8 text-center">
              <Search className="mx-auto h-6 w-6 text-[var(--text-muted)]" />
              <p className="mt-3 text-sm font-semibold">没有匹配的渠道</p>
              <p className="mt-1 text-xs text-[var(--text-muted)]">尝试其他关键词或清除筛选。</p>
            </div>
          )}
        </div>
      )}

      {view !== 'channel' && (
        <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
          <div className="flex flex-wrap items-center gap-2 border-b border-[var(--border)] px-4 py-3 sm:px-5">
            <select
              aria-label="视图"
              value={view}
              onChange={(e) => setView(e.target.value as ViewId)}
              className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-2.5 text-xs outline-none focus:border-[var(--brand)]"
            >
              <option value="channel">渠道列表</option>
              <option value="webhook">Webhook</option>
              <option value="group">接收人组</option>
            </select>
            {view === 'webhook' && (
              <button type="button" onClick={() => setNotice('Webhook 指南接口暂未提供。')} className="ml-auto inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-3 text-xs font-semibold hover:border-[var(--brand)]">
                <Globe className="h-3.5 w-3.5" />接入指南
              </button>
            )}
            {view === 'group' && (
              <button type="button" onClick={() => setCreateGroupOpen(true)} className="ml-auto inline-flex h-9 items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]">
                <Plus className="h-3.5 w-3.5" />新建组
              </button>
            )}
          </div>

          {view === 'webhook' && (
            <div className="space-y-3 p-5">
              {webhooks.map((w) => <WebhookCard key={w.id} webhook={w} />)}
            </div>
          )}

          {view === 'group' && (
            <div className="space-y-3 p-5">
              {groups.map((g) => <GroupCard key={g.id} group={g} />)}
            </div>
          )}
        </div>
      )}

      <CreateGroupModal
        open={createGroupOpen}
        onClose={() => setCreateGroupOpen(false)}
        onCreate={handleCreateGroup}
      />
      <ImportChannelModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImport={handleImport}
      />
      <ExportChannelModal
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        onExport={handleExport}
        total={channels.length}
        selectedCount={selectedIds.length}
      />
    </div>
  );
}
