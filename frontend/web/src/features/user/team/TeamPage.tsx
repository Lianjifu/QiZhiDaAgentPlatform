import { Bot, Check, ChevronRight, FileCheck2, FileText, Heart, MailPlus, MessageSquareText, Share2, UsersRound } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { CenterModal } from '@/components/feedback/CenterModal';
import { NoticeBanner } from '@/components/feedback/NoticeBanner';
import { SideDrawer } from '@/components/feedback/SideDrawer';
import { CardActionButton, CardActions, CatalogToolbar, EmptyFilterState, PageIntro, WorkspacePage } from '../components';
import { useMembers, useSharedItems, useTeams } from './useTeam';
import type { Member, SharedItem, SharedKind, Team } from './schema';

type TabLabel = '成员' | '智能体' | '知识' | '产出物';
type TabValue = 'members' | SharedKind;

const TABS: Array<{ label: TabLabel; value: TabValue }> = [
  { label: '成员', value: 'members' },
  { label: '智能体', value: 'agent' },
  { label: '知识', value: 'knowledge' },
  { label: '产出物', value: 'output' },
];

function accentClass(accent: Team['accent']) {
  return accent === 'emerald'
    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300'
    : accent === 'sky'
      ? 'bg-sky-100 text-sky-700 dark:bg-sky-500/20 dark:text-sky-300'
      : 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300';
}

function kindIcon(kind: SharedKind) {
  return kind === 'agent' ? Bot : kind === 'knowledge' ? FileText : FileCheck2;
}

export default function TeamPage() {
  const { data: teams } = useTeams();
  const [activeTeam, setActiveTeam] = useState('');
  useEffect(() => {
    if (!activeTeam && teams[0]?.name) setActiveTeam(teams[0].name);
  }, [activeTeam, teams]);
  const currentTeam = teams.find((item) => item.name === activeTeam) ?? teams[0];
  const teamName = currentTeam?.name ?? teams[0]?.name ?? '';

  const { data: remoteMembers } = useMembers(teamName);
  const { data: remoteShared } = useSharedItems(teamName);
  const [invited, setInvited] = useState<Member[]>([]);
  const [favorites, setFavorites] = useState<string[]>([]);
  const [tab, setTab] = useState<TabValue>('members');
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<SharedItem | Member | null>(null);
  const [inviting, setInviting] = useState(false);
  const [email, setEmail] = useState('');
  const [notice, setNotice] = useState('');

  const members = useMemo(() => {
    const remote = remoteMembers.filter((member) => !invited.some((row) => row.id === member.id));
    return [...invited, ...remote];
  }, [invited, remoteMembers]);

  const visibleMembers = useMemo(
    () => members.filter((member) => (!teamName || member.team === teamName) && `${member.name} ${member.role}`.toLowerCase().includes(query.trim().toLowerCase())),
    [members, teamName, query],
  );
  const visibleItems = useMemo(
    () => remoteShared.filter((item) => (!teamName || item.team === teamName || !item.team) && item.kind === tab && `${item.title} ${item.description} ${item.owner} ${item.label}`.toLowerCase().includes(query.trim().toLowerCase())),
    [remoteShared, teamName, tab, query],
  );
  const resultCount = tab === 'members' ? visibleMembers.length : visibleItems.length;

  const submitInvite = () => {
    const trimmed = email.trim();
    if (!trimmed || !teamName) return;
    const invitee: Member = {
      id: `local-${Date.now()}`,
      name: trimmed,
      role: '待邀请 · 本地记录',
      team: teamName,
      initials: trimmed.slice(0, 1).toUpperCase(),
      color: 'bg-[var(--brand-light)] text-[var(--brand)]',
    };
    setInvited((current) => [invitee, ...current]);
    setTab('members');
    setQuery('');
    setInviting(false);
    setEmail('');
    setNotice(`"${trimmed}"已加入本页待邀请列表，未发送真实邀请。`);
  };

  const isResource = (item: SharedItem | Member): item is SharedItem => 'kind' in item;

  return (
    <WorkspacePage>
      <PageIntro
        title={currentTeam?.name ?? '协作空间'}
        description={currentTeam?.note ?? '查看工作空间成员与已开放的共享内容。'}
        meta={
          <>
            <span>空间 {teams.length}</span>
            <span>成员 {members.filter((member) => !teamName || member.team === teamName).length}</span>
          </>
        }
        actions={
          <button
            type="button"
            onClick={() => setInviting(true)}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]"
          >
            <MailPlus className="h-3.5 w-3.5" />邀请成员
          </button>
        }
      />

      {notice && <NoticeBanner tone="sky" onClose={() => setNotice('')}>{notice}</NoticeBanner>}

      <div className="grid gap-6 xl:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-4">
          <p className="px-2 text-xs font-semibold text-[var(--text-muted)]">协作空间</p>
          <div className="mt-3 space-y-1" role="group" aria-label="选择协作空间">
            {teams.length ? teams.map((team) => (
              <button
                key={team.name}
                type="button"
                aria-pressed={activeTeam === team.name}
                onClick={() => { setActiveTeam(team.name); setQuery(''); setSelected(null); }}
                className={`flex w-full items-center gap-3 rounded-xl p-3 text-left transition ${activeTeam === team.name ? 'bg-[var(--brand-light)] text-[var(--brand)]' : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]'}`}
              >
                <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg ${accentClass(team.accent)}`}>
                  <UsersRound className="h-4 w-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-semibold">{team.name}</span>
                  <span className="mt-0.5 block truncate text-[10px] opacity-70">{team.note}</span>
                </span>
                <ChevronRight className="h-4 w-4 shrink-0" />
              </button>
            )) : (
              <p className="px-2 py-6 text-xs leading-6 text-[var(--text-muted)]">当前租户还没有工作空间。</p>
            )}
          </div>
        </aside>

        <section className="min-w-0 overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border)] px-4 py-3 sm:px-5">
            <div role="tablist" aria-label="共享内容类型" className="flex gap-1 overflow-x-auto rounded-lg border border-[var(--border)] p-1">
              {TABS.map((item) => (
                <button
                  key={item.value}
                  type="button"
                  role="tab"
                  aria-selected={tab === item.value}
                  onClick={() => setTab(item.value)}
                  className={`min-w-16 rounded-md px-3 py-1.5 text-xs font-semibold transition ${tab === item.value ? 'bg-[var(--text)] text-[var(--surface-1)]' : 'text-[var(--text-muted)] hover:bg-[var(--bg-hover)]'}`}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <span className="inline-flex items-center gap-1 rounded-full bg-[var(--success-bg)] px-2.5 py-1 text-[11px] font-semibold text-[var(--success)]">
              <Check className="h-3.5 w-3.5" />工作空间
            </span>
          </div>
          <CatalogToolbar
            search={query}
            onSearch={setQuery}
            searchLabel="搜索团队内容"
            placeholder="搜索成员或共享内容"
            countLabel={`${resultCount} 项`}
          />
          {tab === 'members' ? (
            visibleMembers.length ? (
              <div className="grid gap-3 p-5 md:grid-cols-2">
                {visibleMembers.map((member) => (
                  <button
                    key={member.id}
                    type="button"
                    onClick={() => setSelected(member)}
                    className="flex items-center gap-4 rounded-2xl border border-[var(--border)] p-4 text-left transition hover:border-[var(--brand)] hover:shadow-[var(--shadow-sm)]"
                  >
                    <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl text-sm font-bold ${member.color}`}>{member.initials}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-semibold">{member.name}</span>
                      <span className="mt-1 block truncate text-xs text-[var(--text-muted)]">{member.role}</span>
                    </span>
                    <ChevronRight className="h-4 w-4 shrink-0 text-[var(--text-muted)]" />
                  </button>
                ))}
              </div>
            ) : (
              <EmptyFilterState title="当前视图没有匹配成员" description="切换空间或尝试其他关键词。" />
            )
          ) : visibleItems.length ? (
            <div className="grid gap-4 p-5 md:grid-cols-2 xl:grid-cols-3">
              {visibleItems.map((item) => {
                const Icon = kindIcon(item.kind);
                return (
                  <article key={item.id} className="flex min-h-[200px] flex-col rounded-2xl border border-[var(--border)] p-5 transition hover:border-[var(--brand)] hover:shadow-[var(--shadow-sm)]">
                    <div className="flex items-start justify-between">
                      <span className="grid h-10 w-10 place-items-center rounded-xl bg-[var(--brand-light)] text-[var(--brand)]">
                        <Icon className="h-5 w-5" />
                      </span>
                      <button
                        type="button"
                        aria-label={`${favorites.includes(item.id) ? '取消收藏' : '收藏'}${item.title}`}
                        aria-pressed={favorites.includes(item.id)}
                        onClick={() => setFavorites((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id])}
                        className={`rounded-lg p-2 ${favorites.includes(item.id) ? 'text-rose-500' : 'text-[var(--text-muted)] hover:text-rose-500'}`}
                      >
                        <Heart className="h-4 w-4" fill={favorites.includes(item.id) ? 'currentColor' : 'none'} />
                      </button>
                    </div>
                    <button type="button" onClick={() => setSelected(item)} className="mt-4 text-left">
                      <span className="text-[10px] font-semibold text-[var(--text-muted)]">{item.label} · {item.updated}</span>
                      <h4 className="mt-2 text-sm font-semibold hover:text-[var(--brand)]">{item.title}</h4>
                      <p className="mt-2 line-clamp-2 text-xs leading-6 text-[var(--text-muted)]">{item.description}</p>
                    </button>
                    <p className="mt-3 text-[11px] text-[var(--text-muted)]">由 {item.owner} 共享</p>
                    <CardActions>
                      <CardActionButton onClick={() => setSelected(item)}>查看详情</CardActionButton>
                    </CardActions>
                  </article>
                );
              })}
            </div>
          ) : (
            <EmptyFilterState title="当前视图没有匹配内容" description="切换分类或尝试其他关键词。" />
          )}
        </section>
      </div>

      <SideDrawer
        open={selected !== null}
        onClose={() => setSelected(null)}
        ariaLabel={selected ? (isResource(selected) ? `${selected.title}详情` : `${selected.name}详情`) : '协作详情'}
        eyebrow={<p className="text-[11px] font-semibold text-[var(--brand)]">{teamName || '协作'} · 详情</p>}
        closeLabel="关闭协作详情"
      >
        {selected && (
          <>
            <span className="mt-10 grid h-14 w-14 place-items-center rounded-2xl bg-[var(--brand-light)] text-[var(--brand)]">
              {isResource(selected) ? <Share2 className="h-7 w-7" /> : <UsersRound className="h-7 w-7" />}
            </span>
            <h3 className="mt-5 text-2xl font-semibold">{isResource(selected) ? selected.title : selected.name}</h3>
            <p className="mt-3 text-sm leading-7 text-[var(--text-muted)]">{isResource(selected) ? selected.description : `${selected.role} · ${selected.team}`}</p>
            <div className="mt-8 divide-y divide-[var(--border)] rounded-2xl border border-[var(--border)] px-5">
              <div className="flex justify-between gap-4 py-4 text-xs">
                <span className="text-[var(--text-muted)]">归属空间</span>
                <span className="font-semibold">{selected.team}</span>
              </div>
              <div className="flex justify-between gap-4 py-4 text-xs">
                <span className="text-[var(--text-muted)]">{isResource(selected) ? '共享者' : '参与方式'}</span>
                <span className="font-semibold">{isResource(selected) ? selected.owner : selected.role}</span>
              </div>
              {isResource(selected) && (
                <div className="flex justify-between gap-4 py-4 text-xs">
                  <span className="text-[var(--text-muted)]">最近动态</span>
                  <span className="font-semibold">{selected.updated}</span>
                </div>
              )}
            </div>
            <div className="mt-8 rounded-2xl bg-[var(--bg-elevated)] p-5">
              <p className="flex items-center gap-2 text-xs font-semibold"><MessageSquareText className="h-4 w-4 text-[var(--brand)]" />协作提示</p>
              <p className="mt-2 text-xs leading-6 text-[var(--text-muted)]">成员来自当前登录身份，智能体与知识来自工作空间目录。邀请仅保存在本页，不会发送邮件。</p>
            </div>
          </>
        )}
      </SideDrawer>
      <CenterModal
        open={inviting}
        onClose={() => setInviting(false)}
        ariaLabel="邀请协作者"
        title={`邀请加入 ${teamName || '协作空间'}`}
        description="填写邮箱后将加入本页列表，不会发送邮件。"
        closeLabel="关闭邀请窗口"
        panelClassName="max-w-md"
        onSubmit={(event) => { event.preventDefault(); submitInvite(); }}
        footer={
          <>
            <button type="button" onClick={() => setInviting(false)} className="rounded-xl border border-[var(--border)] px-4 py-2.5 text-sm font-medium">取消</button>
            <button type="submit" disabled={!email.trim() || !teamName} className="inline-flex items-center gap-2 rounded-xl bg-[var(--brand)] px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40">
              <MailPlus className="h-4 w-4" />加入演示列表
            </button>
          </>
        }
      >
        <label className="mt-6 block text-xs font-semibold">协作者邮箱
          <input
            autoFocus
            type="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="name@company.com"
            className="mt-2 h-11 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]"
          />
        </label>
      </CenterModal>
    </WorkspacePage>
  );
}
