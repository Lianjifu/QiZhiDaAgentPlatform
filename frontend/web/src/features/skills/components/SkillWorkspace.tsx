import { Edit3 } from 'lucide-react';
import { NoticeBanner } from '@/components/feedback/NoticeBanner';
import type { Skill } from '../schema';
import { DRAWER_NAV_ITEMS, RISK_BADGE, STATUS_BADGE, TYPE_META } from './constants';
import type { DrawerPanel } from './constants';
import {
  DrawerPanelAgents, DrawerPanelAudit, DrawerPanelBasic, DrawerPanelMonitor,
  DrawerPanelPermission, DrawerPanelRuntime, DrawerPanelSchema, DrawerPanelVersions,
} from './DrawerPanels';

export function SkillWorkspace({
  skill,
  editing,
  panel,
  setPanel,
  onChange,
  onToggleEditing,
  notice,
  onCloseNotice,
  saving,
}: {
  skill: Skill;
  editing: boolean;
  panel: DrawerPanel;
  setPanel: (panel: DrawerPanel) => void;
  onChange: (patch: Partial<Skill>) => void;
  onToggleEditing: () => void;
  notice?: string;
  onCloseNotice?: () => void;
  saving?: boolean;
}) {
  const meta = TYPE_META[skill.type];
  const Icon = meta.icon;
  const badge = STATUS_BADGE[skill.status];
  const risk = RISK_BADGE[skill.risk];

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-4 p-5 pb-16 sm:p-8 xl:px-6">
      {notice && onCloseNotice ? (
        <NoticeBanner tone="violet" onClose={onCloseNotice}>
          {notice}
        </NoticeBanner>
      ) : null}

      <section className="flex min-h-[480px] flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] lg:flex-row">
        <nav aria-label="技能工作区导航" className="flex w-full shrink-0 flex-col gap-1 border-b border-[var(--border)] bg-[var(--bg-elevated)] p-4 lg:w-[260px] lg:border-b-0 lg:border-r">
          <p className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">工作区</p>
          {DRAWER_NAV_ITEMS.map((item) => {
            const ItemIcon = item.icon;
            const active = panel === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setPanel(item.id)}
                aria-pressed={active}
                className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left text-xs font-semibold transition ${active ? 'bg-[var(--brand-light)] text-[var(--brand)]' : 'text-[var(--text-secondary)] hover:bg-[var(--surface-1)]'}`}
              >
                <ItemIcon className="h-4 w-4" />
                {item.label}
              </button>
            );
          })}
        </nav>
        <main className="min-w-0 flex-1 overflow-auto bg-[var(--bg-app)] p-5">
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border)] pb-4">
            <div className="flex min-w-0 items-center gap-3">
              <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${meta.tone}`}>
                <Icon className="h-5 w-5" />
              </span>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-sm font-semibold">{skill.name}</h2>
                  <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${badge.className}`}>
                    <span className={`h-1.5 w-1.5 rounded-full ${badge.dot}`} />
                    {badge.label}
                  </span>
                  <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${risk.className}`}>
                    {risk.label}
                  </span>
                </div>
                <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">{skill.type} · {skill.owner} · {skill.version}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={onToggleEditing}
              disabled={saving}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-[var(--brand)] bg-[var(--surface-1)] px-3 py-1.5 text-sm font-semibold text-[var(--brand)] hover:bg-[var(--brand-light)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Edit3 className="h-3.5 w-3.5" />{editing ? '完成' : '编辑'}
            </button>
          </div>
          <div className={editing ? undefined : '[&_button:not([data-view])]:pointer-events-none [&_input]:pointer-events-none [&_select]:pointer-events-none [&_textarea]:pointer-events-none [&_[role=switch]]:pointer-events-none'}>
            {panel === 'basic' && <DrawerPanelBasic draft={skill} onChange={onChange} />}
            {panel === 'schema' && <DrawerPanelSchema draft={skill} onChange={onChange} />}
            {panel === 'permission' && <DrawerPanelPermission draft={skill} onChange={onChange} />}
            {panel === 'runtime' && <DrawerPanelRuntime draft={skill} onChange={onChange} />}
            {panel === 'versions' && <DrawerPanelVersions draft={skill} />}
            {panel === 'monitor' && <DrawerPanelMonitor draft={skill} />}
            {panel === 'agents' && <DrawerPanelAgents draft={skill} />}
            {panel === 'audit' && <DrawerPanelAudit draft={skill} />}
          </div>
        </main>
      </section>

      <footer className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-[var(--text-muted)]">
        <span>{editing ? '改完后点「完成」保存并退出编辑。' : '当前为只读查看。'}</span>
        <span>{skill.version} · 最近更新 {skill.lastUpdate}</span>
      </footer>
    </div>
  );
}
