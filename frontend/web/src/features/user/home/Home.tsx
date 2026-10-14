import { useTasks } from '../tasks/useTasks';
import { ArrowRight, Bot, CheckCircle2, Clock3, MessageSquarePlus, Search, Workflow } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { PageIntro, WorkspacePage } from '../components';
import MyInsights from './MyInsights';

const quickActions = [
  { label: '新建对话', description: '描述目标并开始', href: '/copilot', icon: MessageSquarePlus },
  { label: '选择智能体', description: '使用已授权助手', href: '/agents', icon: Bot },
  { label: '查找知识', description: '检索企业资料', href: '/knowledge', icon: Search },
  { label: '选择工作流', description: '运行团队流程', href: '/automations', icon: Workflow },
] as const;

export default function Home() {
  const tasks = useTasks();
  const pendingItems = (tasks.data ?? []).filter((task) => task.status === '待处理').map((task) => ({ id: task.id, title: task.title, meta: `${task.source} · ${task.status}`, href: '/tasks' }));
  return (
    <WorkspacePage>
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6">
        <PageIntro
          title="待我处理"
          description="需要确认或跟进的事项会集中显示在这里。"
          meta={<span>{pendingItems.length} 项待处理</span>}
          actions={
            <NavLink to="/tasks" className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--border)] px-3 text-xs font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]">
              查看全部任务 <ArrowRight className="h-3.5 w-3.5" />
            </NavLink>
          }
        />
        <div className="mt-5 space-y-3">
          {pendingItems.map((item) => (
            <div key={item.id} className="flex items-center gap-3 rounded-xl bg-[var(--warning-bg)]/60 p-4">
              <span className="grid h-9 w-9 place-items-center rounded-lg bg-[var(--warning-bg)] text-[var(--warning)]">
                <Clock3 className="h-4 w-4" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold">{item.title}</p>
                <p className="mt-1 text-xs text-[var(--text-muted)]">{item.meta}</p>
              </div>
              <NavLink to={item.href} className="rounded-md bg-[var(--surface-1)] px-3 py-1.5 text-xs font-medium text-[var(--brand)] shadow-sm">
                处理
              </NavLink>
            </div>
          ))}
          {pendingItems.length === 0 && !tasks.isLoading && !tasks.isError && <div className="flex items-center gap-3 rounded-xl border border-dashed border-[var(--border)] p-4">
            <span className="grid h-9 w-9 place-items-center rounded-lg bg-[var(--success-bg)] text-[var(--success)]">
              <CheckCircle2 className="h-4 w-4" />
            </span>
            <div>
              <p className="text-sm font-semibold">暂无其他待处理事项</p>
              <p className="mt-1 text-xs text-[var(--text-muted)]">新的确认和任务会显示在这里</p>
            </div>
          </div>}
        </div>
      </section>

      <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6">
        <PageIntro title="快捷入口" description="从常用能力快速进入工作。" />
        <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          {quickActions.map(({ label, description, href, icon: Icon }) => (
            <NavLink
              key={href}
              to={href}
              className="group flex items-center gap-3 rounded-xl border border-[var(--border)] px-3.5 py-3 transition hover:border-[var(--brand)] hover:bg-[var(--bg-elevated)]"
            >
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[var(--brand-light)] text-[var(--brand)]">
                <Icon className="h-4 w-4" />
              </span>
              <span className="min-w-0">
                <strong className="block text-sm font-semibold">{label}</strong>
                <span className="mt-0.5 block truncate text-xs text-[var(--text-muted)]">{description}</span>
              </span>
              <ArrowRight className="ml-auto h-4 w-4 shrink-0 text-[var(--text-muted)] transition group-hover:translate-x-0.5 group-hover:text-[var(--brand)]" />
            </NavLink>
          ))}
        </div>
      </section>

      <MyInsights embedded />
    </WorkspacePage>
  );
}
