/**
 * Admin 渠道详情 — 独立页面 /admin/notifications/:id
 */
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Megaphone, Save } from 'lucide-react';
import type { NotificationChannel } from './schema';
import { useDeliveryEvents, useNotificationChannels, useUpdateChannel } from './useNotifications';
import {
  DrawerPanelAudit,
  DrawerPanelDetail,
  DrawerPanelTemplate,
  DrawerSidebar,
} from './components/ChannelDetailDrawer';
import { KIND_META, STATUS_BADGE, type DrawerPanel } from './components/constants';
import { AdminPage } from '@/components/feedback/AdminPage';
import { DetailHeader } from '@/components/feedback/DetailLayout';

function NotFound() {
  return (
    <AdminPage density="lg">
      <Link to="/admin/notifications" className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--brand)]">
        <ArrowLeft className="h-3.5 w-3.5" />返回渠道配置
      </Link>
      <div className="rounded-2xl border border-dashed border-[var(--border)] bg-[var(--surface-1)] p-8 text-center">
        <p className="text-sm font-semibold">渠道不存在或已被删除</p>
        <p className="mt-1 text-xs text-[var(--text-muted)]">请返回列表重新选择。</p>
      </div>
    </AdminPage>
  );
}

export default function ChannelDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: channels = [] } = useNotificationChannels();
  const { data: events = [] } = useDeliveryEvents();
  const updateChannel = useUpdateChannel();

  const original = useMemo(() => channels.find((c) => c.id === id), [channels, id]);
  const [draft, setDraft] = useState<NotificationChannel | null>(null);
  const [panel, setPanel] = useState<DrawerPanel>('detail');

  useEffect(() => {
    setDraft(original ?? null);
    setPanel('detail');
  }, [original?.id]);

  if (!original || !draft) return <NotFound />;

  const meta = KIND_META[draft.kind];
  const Icon = meta.icon;
  const badge = STATUS_BADGE[draft.status];
  const update = (patch: Partial<NotificationChannel>) => setDraft({ ...draft, ...patch });

  const handleSave = () => {
    const { id: channelId, ...patch } = draft;
    updateChannel.mutate({ id: channelId, patch }, { onSuccess: () => navigate('/admin/notifications') });
  };

  return (
    <AdminPage density="lg">
      <Link to="/admin/notifications" className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--brand)]">
        <ArrowLeft className="h-3.5 w-3.5" />返回渠道配置
      </Link>

      <DetailHeader
  eyebrow={<>渠道配置 · {meta.label}</>}
  title={draft.name}
  subtitle={draft.description}
  badges={[{ label: meta.label, className: meta.tone, icon: Icon }]}
  icon={Megaphone}
  iconClass="bg-[var(--brand-light)] text-[var(--brand)]"
/>

      <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6">
        <div className="flex flex-col gap-5 sm:flex-row">
          <DrawerSidebar panel={panel} setPanel={setPanel} />
          <div className="flex-1 space-y-5 sm:pl-6">
            {panel === 'detail' && <DrawerPanelDetail channel={draft} onChange={update} />}
            {panel === 'template' && <DrawerPanelTemplate channel={draft} onChange={update} />}
            {panel === 'audit' && <DrawerPanelAudit channel={draft} events={events} />}
          </div>
        </div>
        <div className="mt-6 flex flex-wrap items-center justify-end gap-3 border-t border-[var(--border)] pt-5">
          <Link to="/admin/notifications" className="rounded-lg border border-[var(--border)] px-4 py-2 text-xs font-semibold">关闭</Link>
          <button type="button" onClick={handleSave} className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--brand)] px-4 py-2 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]">
            <Save className="h-3.5 w-3.5" />保存修改
          </button>
        </div>
      </section>
    </AdminPage>
  );
}
