/**
 * 新建渠道 — 独立页面 /admin/notifications/new
 */
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, Plus } from 'lucide-react';
import { ChannelCreateForm } from './components/ChannelCreateForm';
import { useCreateChannel } from './useNotifications';
import { AdminPage } from '@/components/feedback/AdminPage';

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

      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--brand)]">渠道配置</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">新建渠道</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--text-muted)]">
            选择飞书、企业微信、钉钉或 Web，配置对接凭证后即可对话。
          </p>
        </div>
        <span className="grid h-12 w-12 place-items-center rounded-2xl bg-[var(--brand-light)] text-[var(--brand)]">
          <Plus className="h-5 w-5" />
        </span>
      </header>

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
