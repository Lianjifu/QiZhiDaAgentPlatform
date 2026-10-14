/**
 * EntryDetailDrawer — SideDrawer 包 eyebrow + 4-panel + 立即处置 footer。
 */
import { useEffect, useState } from 'react';
import { ShieldAlert, ShieldOff } from 'lucide-react';
import { SideDrawer } from '@/components/feedback/SideDrawer';
import type { AuditEntry, AuditRule, AuditDrawerPanel } from '../schema';
import { DRAWER_NAV, SEVERITY_BADGE } from './constants';
import { DrawerPanelOverview, DrawerPanelArgs, DrawerPanelRule, DrawerPanelLog } from './DrawerPanels';

function DrawerSidebar({ panel, setPanel }: { panel: AuditDrawerPanel; setPanel: (p: AuditDrawerPanel) => void }) {
  return (
    <nav aria-label="审计工作区" className="hidden w-[200px] shrink-0 flex-col gap-1 border-r border-[var(--border)] bg-[var(--bg-elevated)] p-4 sm:flex">
      <p className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">工作区</p>
      {DRAWER_NAV.map((item) => {
        const Icon = item.icon;
        const active = panel === item.id;
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => setPanel(item.id)}
            aria-pressed={active}
            className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left text-xs font-semibold transition ${active ? 'bg-[var(--brand-light)] text-[var(--brand)]' : 'text-[var(--text-secondary)] hover:bg-[var(--surface-1)]'}`}
          >
            <Icon className="h-4 w-4" />
            {item.label}
          </button>
        );
      })}
    </nav>
  );
}

interface EntryDetailDrawerProps {
  entry: AuditEntry | null;
  rules: AuditRule[];
  onClose: () => void;
  onResolve: (message: string) => void;
}

export function EntryDetailDrawer({ entry, rules, onClose, onResolve }: EntryDetailDrawerProps) {
  const [panel, setPanel] = useState<AuditDrawerPanel>('overview');
  useEffect(() => {
    setPanel('overview');
  }, [entry?.id]);
  if (!entry) return null;
  const sev = SEVERITY_BADGE[entry.severity];
  return (
    <SideDrawer
      open={entry !== null}
      onClose={onClose}
      ariaLabel={`审计条目 ${entry.id}`}
      panelClassName="max-w-3xl"
      closeLabel="关闭审计详情"
      eyebrow={
        <div className="flex items-center gap-2">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-rose-100 text-rose-700 dark:bg-rose-500/20 dark:text-rose-300">
            <ShieldAlert className="h-4 w-4" />
          </span>
          <p className="text-[11px] font-semibold tracking-[0.2em] text-rose-700 dark:text-rose-300">工具审计</p>
        </div>
      }
    >
      <div className="mt-8">
        <h3 className="font-mono text-2xl font-semibold">{entry.id}</h3>
        <p className="mt-2 text-sm leading-6 text-[var(--text-muted)]">
          记录工具调用 · 权限校验 · 风险命中全过程,用于事后追责与策略优化。
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-[11px] font-semibold ${sev.className}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${sev.dot}`} aria-hidden="true" />
            {sev.label}
          </span>
          <span className="rounded-full bg-[var(--bg-elevated)] px-2 py-1 font-mono text-[11px] font-medium">{entry.toolName}</span>
        </div>
      </div>
      <div className="mt-8 flex flex-col sm:flex-row">
        <DrawerSidebar panel={panel} setPanel={setPanel} />
        <div className="flex-1 space-y-5 sm:pl-6">
          {panel === 'overview' && <DrawerPanelOverview entry={entry} />}
          {panel === 'args' && <DrawerPanelArgs entry={entry} />}
          {panel === 'rule' && <DrawerPanelRule entry={entry} rules={rules} />}
          {panel === 'log' && <DrawerPanelLog entry={entry} />}
        </div>
      </div>
      <div className="mt-8 flex items-center justify-end gap-2 border-t border-[var(--border)] pt-5">
        <button type="button" onClick={onClose} className="rounded-lg border border-[var(--border)] px-4 py-2 text-xs font-semibold">
          关闭
        </button>
        <button
          type="button"
          onClick={() => onResolve('已标记处置')}
          className="inline-flex items-center gap-1.5 rounded-lg bg-rose-600 px-4 py-2 text-xs font-semibold text-white hover:bg-rose-700"
        >
          <ShieldOff className="h-3.5 w-3.5" />
          立即处置
        </button>
      </div>
    </SideDrawer>
  );
}
