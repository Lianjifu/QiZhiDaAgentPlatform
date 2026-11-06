/**
 * 新建渠道 — 独立页面 /admin/notifications/new
 */
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, Plus } from 'lucide-react';
import { ChannelCreateForm } from './components/ChannelCreateForm';
import { useCreateChannel } from './useNotifications';
import { AdminPage } from '@/components/feedback/AdminPage';
import { DetailHeader } from '@/components/feedback/DetailLayout';

export default function ChannelCreatePage() {
  const navigate = useNavigate();
  const createChannel = useCreateChannel();

  return (
    <AdminPage density="lg">
      <Link
        to="/admin/notifications"
        className="inline-flex w-fit items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--brand)]"
      >
        <ArrowLeft className="h-3.5 w-3.5" />返回渠道配置
      </Link>

      <DetailHeader
  eyebrow="渠道配置"
  title="新建渠道"
  subtitle="选择飞书、企业微信、钉钉或 Web，配置对接凭证后即可对话。"
  icon={Plus}
  iconClass="bg-[var(--brand-light)] text-[var(--brand)]"
/>

      <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6">
        <ChannelCreateForm
          onCancel={() => navigate('/admin/notifications')}
          isPending={createChannel.isPending}
          onSubmit={(vars) =>
            createChannel.mutate(vars, {
              onSuccess: (created) => navigate(`/admin/notifications/${created.id}`),
              onError: () => navigate('/admin/notifications'),
            })
          }
        />
      </section>
    </AdminPage>
  );
}
