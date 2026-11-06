/**
 * 用户侧「首页」 ✓ —— 快捷入口 ✓ + 我的洞察 ✓。
 *
 * ⚠️ **「待我处理」搬走了** ✓ —— 它本来就是 ``/api/tasks`` 的一个过滤视图 ✓
 * （与「任务」页同一份数据 ✓ —— 两处渲染 ✗✗），现在只在**任务页**里有 ✓。
 */
import { ArrowRight, Boxes, ListTodo, MessageSquarePlus, Search, Workflow } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { PageIntro, WorkspacePage } from '../components';
import MyInsights from './MyInsights';

const quickActions = [
  { label: '新建对话', description: '描述目标并开始', href: '/copilot', icon: MessageSquarePlus },
  { label: '资源库', description: '选用智能体与能力', href: '/library', icon: Boxes },
  { label: '查找知识', description: '检索企业资料', href: '/library?tab=knowledge', icon: Search },
  { label: '选择工作流', description: '运行团队流程', href: '/library?tab=automations', icon: Workflow },
  { label: '我的任务', description: '查看执行中的工作', href: '/tasks', icon: ListTodo },
] as const;

export default function Home() {
  return (
    <WorkspacePage>
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6">
        <PageIntro title="快捷入口" description="从常用能力快速进入工作。" />
        <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
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
