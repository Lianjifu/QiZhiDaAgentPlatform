import { ArrowRight, Bot, FileText, Heart, MessageSquareText, ShieldCheck, Sparkles, UsersRound } from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type MouseEvent } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { SideDrawer } from '@/components/feedback/SideDrawer';
import { CardActionButton, CardActions, CatalogToolbar, EmptyFilterState, PageIntro, WorkspacePage } from '../components';
import { BrowseAndUseDrawer } from './components/BrowseAndUseDrawer';
import { useAgents } from './useAgents';
import type { Agent, AgentCategory } from './schema';

const CHOSEN_STORAGE_KEY = 'qzdap.user.agents.chosen';

const ICON_BY_CATEGORY: Record<AgentCategory, typeof UsersRound> = {
  '销售支持': UsersRound,
  '企业通用': FileText,
  '客服应答': ShieldCheck,
  '数据分析': Bot,
  '文案创作': Sparkles,
};

const CATEGORY_LABEL: Record<'all' | AgentCategory, string> = {
  all: '全部场景', '销售支持': '销售支持', '企业通用': '企业通用', '客服应答': '客服应答', '数据分析': '数据分析', '文案创作': '文案创作',
};

function readChosenIds(): string[] {
  try {
    const raw = sessionStorage.getItem(CHOSEN_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string') : [];
  } catch {
    return [];
  }
}

export default function AgentsPage() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { data: remoteList = [], isLoading, isFetching, refetch } = useAgents();
  const agents = remoteList;

  const [category, setCategory] = useState<'all' | AgentCategory>('all');
  const [query, setQuery] = useState('');
  const [onlyFavorites, setOnlyFavorites] = useState(false);
  const [favorites, setFavorites] = useState<string[]>([]);
  const [chosenIds, setChosenIds] = useState<string[]>(() => readChosenIds());
  const [browseOpen, setBrowseOpen] = useState(false);
  const [selected, setSelected] = useState<Agent | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const browseTriggerRef = useRef<HTMLButtonElement | null>(null);
  const isTeamView = pathname === '/team/agents';

  useEffect(() => {
    sessionStorage.setItem(CHOSEN_STORAGE_KEY, JSON.stringify(chosenIds));
  }, [chosenIds]);

  // 目录里已下线的选用项自动清理
  useEffect(() => {
    if (agents.length === 0) return;
    const openIds = new Set(agents.map((agent) => agent.id));
    setChosenIds((current) => {
      const next = current.filter((id) => openIds.has(id));
      return next.length === current.length ? current : next;
    });
  }, [agents]);

  const chosenAgents = useMemo(
    () => agents.filter((agent) => chosenIds.includes(agent.id)),
    [agents, chosenIds],
  );

  const categoryOptions = useMemo(() => {
    const present = Array.from(new Set(chosenAgents.map((agent) => agent.category))) as AgentCategory[];
    return (['all', ...present] as Array<'all' | AgentCategory>);
  }, [chosenAgents]);

  const visible = useMemo(() => chosenAgents.filter((agent) =>
    (category === 'all' || agent.category === category) &&
    (!onlyFavorites || favorites.includes(agent.id)) &&
    `${agent.name} ${agent.description} ${agent.category} ${agent.owner}`.toLowerCase().includes(query.trim().toLowerCase()),
  ), [chosenAgents, category, onlyFavorites, favorites, query]);

  const openDetails = (agent: Agent, event: MouseEvent<HTMLButtonElement>) => {
    triggerRef.current = event.currentTarget;
    setSelected(agent);
  };
  const closeDetails = () => {
    setSelected(null);
    triggerRef.current?.focus();
  };
  const toggleFavorite = (id: string) => setFavorites((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  const toggleChosen = (id: string) => setChosenIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  const startConversation = (agent: Agent) => {
    if (!chosenIds.includes(agent.id)) {
      setChosenIds((current) => [...current, agent.id]);
    }
    navigate('/copilot', {
      state: {
        agentId: agent.id,
        agentName: agent.name,
        agentExample: agent.example,
      },
    });
  };
  const resetFilters = () => { setQuery(''); setCategory('all'); setOnlyFavorites(false); };

  const browseAndUse = async () => {
    browseTriggerRef.current = document.activeElement instanceof HTMLButtonElement
      ? document.activeElement
      : browseTriggerRef.current;
    setBrowseOpen(true);
    await refetch();
  };

  const closeBrowse = () => {
    setBrowseOpen(false);
    browseTriggerRef.current?.focus();
  };

  return (
    <WorkspacePage>
      <PageIntro
        title={isTeamView ? '团队智能体' : '智能体'}
        description={isTeamView ? '来自智能体管理、已对工作区开放的助手。' : '从管理员已发布的智能体中选用，进入对话完成工作。'}
        meta={
          <>
            <span>开放 {agents.length}</span>
            <span>已选用 {chosenAgents.length}</span>
            <span>收藏 {favorites.length}</span>
            {(isLoading || isFetching) && <span>同步中…</span>}
          </>
        }
        actions={
          <button
            ref={browseTriggerRef}
            type="button"
            onClick={() => { void browseAndUse(); }}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]"
          >
            <MessageSquareText className="h-3.5 w-3.5" />浏览并选用
          </button>
        }
      />

      <section id="agent-catalog" aria-labelledby="agent-catalog-title" className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
        <h2 id="agent-catalog-title" className="sr-only">已选用智能体</h2>
        <CatalogToolbar
          search={query}
          onSearch={setQuery}
          searchLabel="搜索智能体"
          placeholder="搜索智能体、场景或团队"
          filters={[
            {
              label: '场景',
              value: category,
              onChange: (value) => setCategory(value as 'all' | AgentCategory),
              options: categoryOptions.map((item) => ({ value: item, label: CATEGORY_LABEL[item] ?? item })),
            },
            {
              label: '收藏筛选',
              value: onlyFavorites ? 'favorites' : 'all',
              onChange: (value) => setOnlyFavorites(value === 'favorites'),
              options: [
                { value: 'all', label: '全部' },
                { value: 'favorites', label: '仅收藏' },
              ],
            },
          ]}
          countLabel={`${visible.length} 项`}
        />
        {visible.length ? (
          <div className="grid gap-4 p-5 md:grid-cols-2 xl:grid-cols-3">
            {visible.map((agent) => {
              const Icon = ICON_BY_CATEGORY[agent.category] ?? Bot;
              const favorite = favorites.includes(agent.id);
              return (
                <article key={agent.id} className="group flex min-h-[248px] min-w-0 flex-col rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 transition hover:border-[var(--brand)] hover:shadow-[var(--shadow-sm)]">
                  <div className="flex items-start justify-between gap-3">
                    <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${agent.tone}`}><Icon className="h-5 w-5" /></span>
                    <button type="button" aria-label={`${favorite ? '取消收藏' : '收藏'}${agent.name}`} aria-pressed={favorite} onClick={() => toggleFavorite(agent.id)} className={`rounded-lg p-2 transition ${favorite ? 'text-rose-600' : 'text-[var(--text-muted)] hover:text-rose-600'}`}>
                      <Heart className="h-4 w-4" fill={favorite ? 'currentColor' : 'none'} />
                    </button>
                  </div>
                  <p className="mt-4 text-[11px] font-medium text-[var(--text-muted)]">{agent.category} · {agent.owner}</p>
                  <button type="button" onClick={(event) => openDetails(agent, event)} className="mt-1 text-left text-base font-semibold hover:text-[var(--brand)]">{agent.name}</button>
                  <p className="mt-2 line-clamp-2 text-xs leading-6 text-[var(--text-muted)]">{agent.description}</p>
                  <CardActions>
                    <CardActionButton onClick={(event) => openDetails(agent, event)}>了解详情</CardActionButton>
                    <CardActionButton tone="brand" aria-label={`与${agent.name}开始对话`} onClick={() => startConversation(agent)}>
                      <MessageSquareText className="h-3.5 w-3.5" />开始对话
                    </CardActionButton>
                  </CardActions>
                </article>
              );
            })}
          </div>
        ) : (
          <EmptyFilterState
            title={chosenAgents.length === 0 ? (agents.length === 0 ? '管理员尚未开放智能体' : '还没有选用智能体') : '没有找到符合条件的智能体'}
            description={
              chosenAgents.length === 0
                ? (agents.length === 0
                  ? '请在智能体管理中发布并开放给工作区后再来选用。'
                  : '点击右上角「浏览并选用」，从开放目录中勾选需要的助手。')
                : '试试其他关键词，或清除筛选后重新查看。'
            }
            action={
              chosenAgents.length === 0 && agents.length > 0 ? (
                <button type="button" onClick={() => { void browseAndUse(); }} className="text-xs font-semibold text-[var(--brand)] hover:underline">
                  去浏览并选用
                </button>
              ) : chosenAgents.length > 0 ? (
                <button type="button" onClick={resetFilters} className="text-xs font-semibold text-[var(--brand)] hover:underline">清除筛选</button>
              ) : null
            }
          />
        )}
      </section>

      <BrowseAndUseDrawer
        open={browseOpen}
        agents={agents}
        chosenIds={chosenIds}
        loading={isLoading || isFetching}
        onClose={closeBrowse}
        onToggleChosen={toggleChosen}
        onStartConversation={startConversation}
      />

      <SideDrawer
        open={selected !== null}
        onClose={closeDetails}
        ariaLabel={selected ? `${selected.name}详情` : '智能体详情'}
        eyebrow={<p className="text-[11px] font-semibold text-[var(--brand)]">智能体详情</p>}
        closeLabel="关闭智能体详情"
      >
        {selected && (() => {
          const Icon = ICON_BY_CATEGORY[selected.category] ?? Bot;
          return (
            <>
              <div className={`mt-10 grid h-14 w-14 place-items-center rounded-2xl ${selected.tone}`}>
                <Icon className="h-7 w-7" />
              </div>
              <h2 className="mt-5 text-2xl font-semibold">{selected.name}</h2>
              <p className="mt-2 text-xs text-[var(--text-muted)]">{selected.category} · {selected.owner} · 已选用</p>
              <p className="mt-6 text-sm leading-7 text-[var(--text-secondary)]">{selected.description}</p>
              <div className="mt-7 grid gap-3 sm:grid-cols-2">
                <div className="rounded-xl bg-[var(--bg-elevated)] p-4">
                  <p className="text-xs text-[var(--text-muted)]">适合处理</p>
                  <p className="mt-2 text-sm font-semibold leading-6">{selected.useCase}</p>
                </div>
                <div className="rounded-xl bg-[var(--bg-elevated)] p-4">
                  <p className="text-xs text-[var(--text-muted)]">预期产出</p>
                  <p className="mt-2 text-sm font-semibold leading-6">{selected.output}</p>
                </div>
              </div>
              <div className="mt-5 rounded-xl border border-[var(--border)] p-4">
                <p className="text-xs font-semibold">开始前准备</p>
                <p className="mt-2 text-xs leading-6 text-[var(--text-muted)]">{selected.input}。生成内容仅供参考，重要结果需人工核对；涉及外部发送或数据修改时应先确认。</p>
              </div>
              <div className="mt-7 flex flex-col gap-2 sm:flex-row">
                <button type="button" onClick={() => toggleFavorite(selected.id)} className="inline-flex items-center justify-center gap-2 rounded-xl border border-[var(--border)] px-4 py-2.5 text-sm font-semibold">
                  <Heart className="h-4 w-4" fill={favorites.includes(selected.id) ? 'currentColor' : 'none'} />
                  {favorites.includes(selected.id) ? '取消收藏' : '收藏'}
                </button>
                <button type="button" onClick={() => toggleChosen(selected.id)} className="inline-flex items-center justify-center gap-2 rounded-xl border border-[var(--border)] px-4 py-2.5 text-sm font-semibold">
                  {chosenIds.includes(selected.id) ? '取消选用' : '选用'}
                </button>
                <button type="button" onClick={() => startConversation(selected)} className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl bg-[var(--brand)] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[var(--brand-hover)]">
                  <MessageSquareText className="h-4 w-4" />与{selected.name}开始对话<ArrowRight className="h-4 w-4" />
                </button>
              </div>
              <p className="mt-5 text-xs text-[var(--text-muted)]">数据来自智能体管理中已开放的条目。</p>
            </>
          );
        })()}
      </SideDrawer>
    </WorkspacePage>
  );
}
