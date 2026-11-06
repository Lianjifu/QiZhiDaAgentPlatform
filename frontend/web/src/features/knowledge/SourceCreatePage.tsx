/**
 * 新增数据源 — 独立页面 /admin/knowledge/sources/new
 *
 * 顶部返回按钮回 /admin/knowledge;
 * 内部 <SourceCreateModal> 复用现有 body(已从 CenterModal 拆壳);
 * 提交成功后跳回知识管理列表。
 */
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, Database } from 'lucide-react';
import { useCreateSource } from './useKnowledge';
import SourceCreateModal from './components/SourceCreateModal';
import { AdminPage } from '@/components/feedback/AdminPage';

export default function SourceCreatePage() {
  const navigate = useNavigate();
  const createSource = useCreateSource();

  return (
    <AdminPage density="lg">
      <Link
        to="/admin/knowledge"
        className="inline-flex w-fit items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--brand)]"
      >
        <ArrowLeft className="h-3.5 w-3.5" />返回知识管理
      </Link>

      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--brand)]">知识管理</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">新增数据源</h1>
        </div>
        <p className="max-w-sm text-xs leading-5 text-[var(--text-muted)]">
          填写名称、类型与同步频率,创建后可关联到具体知识库。
        </p>
      </header>

      <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6">
        <div className="mb-5 flex items-center gap-2 border-b border-[var(--border)] pb-4">
          <Database className="h-4 w-4 text-[var(--brand)]" />
          <h2 className="text-sm font-semibold">数据源配置</h2>
        </div>
        <SourceCreateModal
          onCancel={() => navigate('/admin/knowledge')}
          onSubmit={(vars) =>
            createSource.mutate(vars, {
              onSuccess: () => navigate('/admin/knowledge'),
              onError: () => navigate('/admin/knowledge'),
            })
          }
          isPending={createSource.isPending}
        />
      </section>
    </AdminPage>
  );
}