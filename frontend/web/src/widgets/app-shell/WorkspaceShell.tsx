import { useEffect, useState } from 'react';
import { Menu, PanelLeftClose, PanelLeftOpen, X } from 'lucide-react';
import { NavLink, Navigate, Outlet, useLocation } from 'react-router-dom';
import { childPageTitle, PageCrumbNav } from './pageCrumb';
import { BrandLogo } from '@/components/feedback/BrandLogo';
import { useAuthStore } from '@/features/auth';
import { defaultRouteForRole, pathAllowedForRole } from '@/features/auth/roleRoutes';
import { useUiStore } from '@/stores/uiStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { adminNavigationSections, adminUtilityNavigation, utilityNavigation, workspaceNavigation, type NavigationItem } from './navigation';
import { UserFooter } from './UserFooter';

function resolvePage(pathname: string, isAdminArea: boolean): { item?: NavigationItem; section?: string } {
  const groups = isAdminArea
    ? [
        ...adminNavigationSections.map((section) => ({ section: section.title, items: section.items })),
        { section: undefined as string | undefined, items: adminUtilityNavigation },
      ]
    : [{ section: undefined as string | undefined, items: [...workspaceNavigation, ...utilityNavigation] }];
  let best: { item: NavigationItem; section?: string } | null = null;
  for (const group of groups) {
    for (const item of group.items) {
      const matched = pathname === item.href || pathname.startsWith(`${item.href}/`);
      if (!matched) continue;
      if (!best || item.href.length > best.item.href.length) best = { item, section: group.section };
    }
  }
  return { item: best?.item, section: best?.section };
}

function NavigationLink({ item, collapsed, onNavigate }: { item: NavigationItem; collapsed: boolean; onNavigate: () => void }) {
  const Icon = item.icon;
  return (
    <NavLink
      to={item.href}
      onClick={onNavigate}
      title={collapsed ? `${item.label}：${item.description}` : item.description}
      className={({ isActive }) => `group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${
        isActive ? 'bg-[var(--brand-light)] font-semibold text-[var(--brand)]' : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text)]'
      }`}
    >
      <Icon className="h-[18px] w-[18px] shrink-0" />
      <span className={collapsed ? 'sr-only' : 'truncate'}>{item.label}</span>
    </NavLink>
  );
}

export function WorkspaceShell() {
  const location = useLocation();
  const isAuthed = useAuthStore((state) => state.isAuthed);
  const user = useAuthStore((state) => state.user);
  const [hydrated, setHydrated] = useState(() => useAuthStore.persist.hasHydrated());
  useEffect(() => {
    if (useAuthStore.persist.hasHydrated()) {
      setHydrated(true);
      return;
    }
    return useAuthStore.persist.onFinishHydration(() => setHydrated(true));
  }, []);
  const workspace = useWorkspaceStore((state) => state.current);
  const { sidebarCollapsed, toggleSidebar, mobileDrawerOpen, closeMobileDrawer, openMobileDrawer } = useUiStore();
  if (!hydrated) return null;
  if (!isAuthed) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  const homeHref = defaultRouteForRole(user?.role);
  if (!pathAllowedForRole(location.pathname, user?.role)) {
    return <Navigate to={homeHref} replace />;
  }
  const isAdmin = user?.role === 'admin';
  const workspaceName = workspace?.name ?? '默认工作区';
  const isAdminArea = isAdmin && location.pathname.startsWith('/admin');
  const page = resolvePage(location.pathname, isAdminArea);
  const PageIcon = page.item?.icon;
  const pageLabel = page.item?.label ?? '首页';
  const pageHint = [page.section, page.item?.description].filter(Boolean).join(' · ');
  const childTitle = childPageTitle(location.pathname);

  const sidebar = (
    <aside className={`flex h-full flex-col border-r border-[var(--border)] bg-[var(--surface-1)] px-3 py-4 ${sidebarCollapsed ? 'w-[76px]' : 'w-[248px]'}`}>
      <div className={`flex items-center ${sidebarCollapsed ? 'justify-center' : 'justify-between'} px-2`}>
        <NavLink to={homeHref} className="flex items-center gap-2.5" aria-label="返回首页">
          {sidebarCollapsed ? (
            <BrandLogo size={36} className="text-[var(--brand)]" ariaLabel="企智搭 · 智能体平台" />
          ) : (
            <BrandLogo size={36} withWordmark className="text-[var(--brand)]" />
          )}
        </NavLink>
        <button type="button" onClick={toggleSidebar} className="hidden rounded-md p-1.5 text-[var(--text-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--text)] lg:block" aria-label={sidebarCollapsed ? '展开侧栏' : '收起侧栏'} title={sidebarCollapsed ? '展开侧栏' : '收起侧栏'}>
          {sidebarCollapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
        </button>
      </div>
      <nav className="mt-7 flex-1 overflow-y-auto" aria-label="智能体工作台导航">
        {isAdminArea ? (
          <div className="space-y-5">
            {adminNavigationSections.map((section, index) => (
              <div key={section.title} className={`${index === 0 ? '' : 'border-t border-[var(--border)] pt-4'} space-y-1`}>
                {!sidebarCollapsed && (
                  <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">{section.title}</p>
                )}
                {section.items.map((item) => <NavigationLink key={item.href} item={item} collapsed={sidebarCollapsed} onNavigate={closeMobileDrawer} />)}
              </div>
            ))}
          </div>
        ) : (
          <div className="space-y-1">
            {workspaceNavigation.map((item) => <NavigationLink key={item.href} item={item} collapsed={sidebarCollapsed} onNavigate={closeMobileDrawer} />)}
          </div>
        )}
      </nav>
      <div className="mt-3 border-t border-[var(--border)] pt-3">
        <UserFooter collapsed={sidebarCollapsed} audience={isAdminArea ? 'admin' : 'user'} onNavigate={closeMobileDrawer} />
      </div>
    </aside>
  );

  return (
    <div className="flex min-h-screen bg-[var(--bg-elevated)] text-[var(--text)]">
      <div className="hidden lg:block">{sidebar}</div>
      {mobileDrawerOpen ? <div className="fixed inset-0 z-40 bg-slate-950/40 lg:hidden" onClick={closeMobileDrawer} aria-hidden="true" /> : null}
      <div className={`fixed inset-y-0 left-0 z-50 transition-transform lg:hidden ${mobileDrawerOpen ? 'translate-x-0' : '-translate-x-full'}`}>{sidebar}</div>
      <div className="flex h-svh min-h-0 min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-[var(--border)] bg-[var(--surface-1)] px-4 sm:px-5">
          <div className="flex min-w-0 items-center gap-2.5">
            <button type="button" className="rounded-md p-2 text-[var(--text-muted)] hover:bg-[var(--bg-hover)] lg:hidden" onClick={openMobileDrawer} aria-label="打开导航菜单"><Menu className="h-5 w-5" /></button>
            {PageIcon ? (
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-[var(--brand-light)] text-[var(--brand)]">
                <PageIcon className="h-4 w-4" />
              </span>
            ) : null}
            <div className="min-w-0">
              {childTitle && page.item ? (
                <PageCrumbNav parentHref={page.item.href} parentLabel={pageLabel} title={childTitle} />
              ) : (
                <h1 className="truncate text-sm font-semibold leading-5">{pageLabel}</h1>
              )}
              {pageHint ? <p className="hidden truncate text-[11px] leading-4 text-[var(--text-muted)] sm:block">{pageHint}</p> : null}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <span className="hidden max-w-[11rem] items-center gap-1.5 truncate rounded-full border border-[var(--border)] bg-[var(--bg-elevated)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)] sm:inline-flex">
              <span aria-hidden="true" className="h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--brand)]" />
              <span className="truncate">{workspaceName}</span>
            </span>
            {mobileDrawerOpen ? (
              <button type="button" className="rounded-md p-1 text-[var(--text-muted)] hover:bg-[var(--bg-hover)] lg:hidden" onClick={closeMobileDrawer} aria-label="关闭导航菜单"><X className="h-4 w-4" /></button>
            ) : null}
          </div>
        </header>
        <main id="main-content" className="flex min-h-0 flex-1 flex-col overflow-auto"><Outlet /></main>
      </div>
    </div>
  );
}
