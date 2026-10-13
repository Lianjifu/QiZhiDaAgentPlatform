import { ChevronRight } from 'lucide-react';
import { NavLink } from 'react-router-dom';

const TYPE_LABEL: Record<string, string> = {
  Skill: '新建 Skill',
  Tool: '新建 Tool',
  MCP: '新建 MCP',
};

/** 嵌套页的当前标题。列表页返回 null，顶栏继续显示栏目名。 */
export function childPageTitle(pathname: string, search?: URLSearchParams): string | null {
  if (pathname === '/admin/tools/new') {
    const type = search?.get('type');
    if (type && (TYPE_LABEL[type] || null)) {
      return TYPE_LABEL[type];
    }
    return '新建技能';
  }
  if (
    pathname === '/admin/agents/new'
    || pathname === '/admin/knowledge/kbs/new'
    || pathname === '/admin/knowledge/sources/new'
    || pathname === '/admin/regressions/new'
    || pathname === '/admin/feedback/new'
    || pathname === '/admin/feedback/rules/new'
    || pathname === '/admin/workflows/new'
    || pathname === '/admin/notifications/new'
    || pathname === '/admin/models/new'
    || pathname === '/admin/models/routes/new'
    || pathname === '/admin/quotas/new'
    || pathname === '/admin/quotas/alerts/new'
    || pathname === '/admin/evaluations/new'
    || pathname === '/admin/tool-audit/rules/new'
    || pathname === '/admin/metrics/new'
  ) {
    return '新建页';
  }
  if (/^\/admin\/(?:agents|tools)\/[^/]+\/edit\/?$/.test(pathname)) return '详情页';
  if (/^\/admin\/(?:agents|tools)\/[^/]+\/?$/.test(pathname)) return '详情页';
  if (/^\/admin\/knowledge\/(?:kbs|sources|docs)\/[^/]+\/?$/.test(pathname)) return '详情页';
  if (/^\/admin\/memory\/(?:policies|l1|l2|l3)\/[^/]+\/?$/.test(pathname)) return '详情页';
  if (/^\/admin\/workflows\/[^/]+\/?$/.test(pathname)) return '详情页';
  if (/^\/admin\/evaluations\/[^/]+\/?$/.test(pathname)) return '详情页';
  if (/^\/admin\/regressions\/[^/]+\/?$/.test(pathname)) return '详情页';
  if (/^\/admin\/feedback\/[^/]+\/?$/.test(pathname)) return '详情页';
  if (/^\/admin\/models\/[^/]+\/?$/.test(pathname)) return '详情页';
  if (/^\/admin\/quotas\/[^/]+\/?$/.test(pathname)) return '详情页';
  if (/^\/admin\/notifications\/[^/]+\/?$/.test(pathname)) return '详情页';
  if (/^\/admin\/operations\/[^/]+\/?$/.test(pathname)) return '详情页';
  if (/^\/admin\/tool-audit\/[^/]+\/?$/.test(pathname)) return '详情页';
  if (/^\/admin\/metrics\/[^/]+\/?$/.test(pathname)) return '详情页';
  return null;
}

export function PageCrumbNav({
  parentHref,
  parentLabel,
  title,
}: {
  parentHref: string;
  parentLabel: string;
  title: string;
}) {
  return (
    <nav aria-label="面包屑">
      <ol className="flex min-w-0 items-center gap-1.5 text-sm font-semibold leading-5">
        <li className="min-w-0">
          <NavLink
            to={parentHref}
            end
            className="block truncate rounded-md text-[var(--text-secondary)] hover:text-[var(--brand)]"
          >
            {parentLabel}
          </NavLink>
        </li>
        <li className="flex min-w-0 items-center gap-1.5">
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-[var(--text-muted)]" aria-hidden />
          <h1 className="truncate text-[var(--text)]">{title}</h1>
        </li>
      </ol>
    </nav>
  );
}
