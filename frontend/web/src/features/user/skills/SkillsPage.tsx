import { Bot, Clock3, Heart, Network, Sparkles, Wrench } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { NoticeBanner } from '@/components/feedback/NoticeBanner';
import { CardActionButton, CardActions, CatalogToolbar, EmptyFilterState, PageIntro, WorkspacePage } from '../components';
import { useAgents } from '../agents/useAgents';
import { useCapabilities, useRecordUse, useToggleFavorite } from './useSkills';
import type { Capability, CapabilityType, SkillListParams } from './schema';
import { BrowseCapabilitiesDrawer } from './components/BrowseCapabilitiesDrawer';
import { CapabilityDrawer } from './components/CapabilityDrawer';
import { UseModal } from './components/UseModal';

interface RecentUseItem { id: string; name: string; type: CapabilityType; time: string }

const CHOSEN_STORAGE_KEY = 'qzdap.user.skills.chosen';

const TYPE_META = {
  Skill: { icon: Sparkles, tone: 'bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300', label: '工作技能' },
  Tool: { icon: Wrench, tone: 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300', label: '受控工具' },
  MCP: { icon: Network, tone: 'bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300', label: '外部连接' },
} as const;

const DEFAULT_PARAMS: SkillListParams = { type: 'all', q: '' };

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

export default function SkillsPage() {
  const navigate = useNavigate();
  const [params, setParams] = useState<SkillListParams>(DEFAULT_PARAMS);
  const [favorites, setFavorites] = useState<string[]>([]);
  const [chosenIds, setChosenIds] = useState<string[]>(() => readChosenIds());
  const [browseOpen, setBrowseOpen] = useState(false);
  const [selected, setSelected] = useState<Capability | null>(null);
  const [useTarget, setUseTarget] = useState<Capability | null>(null);
  const [recent, setRecent] = useState<RecentUseItem[]>([]);
  const [notice, setNotice] = useState('');
  const browseTriggerRef = useRef<HTMLButtonElement | null>(null);

  const { data: list = [], isLoading, isFetching, refetch } = useCapabilities();
  const { data: agents = [] } = useAgents();
  const toggleFav = useToggleFavorite();
  const recordUse = useRecordUse();

  useEffect(() => {
    sessionStorage.setItem(CHOSEN_STORAGE_KEY, JSON.stringify(chosenIds));
  }, [chosenIds]);

  useEffect(() => {
    if (list.length === 0) return;
    const openIds = new Set(list.map((item) => item.id));
    setChosenIds((current) => {
      const next = current.filter((id) => openIds.has(id));
      return next.length === current.length ? current : next;
    });
  }, [list]);

  const chosenList = useMemo(
    () => list.filter((item) => chosenIds.includes(item.id)),
    [list, chosenIds],
  );

  const visible = useMemo(() => {
    const q = params.q?.trim().toLowerCase() ?? '';
    return chosenList.filter((item) =>
      (params.type === 'all' || params.type === undefined || item.type === params.type) &&
      (params.status === 'all' || params.status === undefined || item.status === params.status) &&
      (!params.onlyFavorites || favorites.includes(item.id)) &&
      (`${item.name} ${item.description} ${item.owner} ${item.tags.join(' ')} ${item.relatedAgents.join(' ')}`.toLowerCase().includes(q)),
    );
  }, [chosenList, params, favorites]);

  const availableCount = list.filter((item) => item.status === 'available').length;

  const toggleFavorite = (item: Capability) => {
    setFavorites((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id]);
    toggleFav.mutate({ id: item.id, on: !favorites.includes(item.id) });
  };

  const toggleChosen = (id: string) => {
    setChosenIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  };

  const ensureChosen = (id: string) => {
    setChosenIds((current) => current.includes(id) ? current : [...current, id]);
  };

  const openUse = (item: Capability) => {
    if (item.status !== 'available') {
      setNotice('这个能力当前不可用，请选择其他能力。');
      return;
    }
    ensureChosen(item.id);
    setUseTarget(item);
  };

  const confirmUse = (goal: string) => {
    if (!useTarget) return;
    setRecent((current) => [{ id: `recent-${Date.now()}`, name: useTarget.name, type: useTarget.type, time: '刚刚 · 本地演示' }, ...current].slice(0, 5));
    setNotice(`「${useTarget.name}」已加入本地使用记录，未触发真实连接。`);
    recordUse.mutate({ id: useTarget.id, goal });
    setUseTarget(null);
    setBrowseOpen(false);
  };

  const useToolInCopilot = (item: Capability) => {
    ensureChosen(item.id);
    navigate('/copilot', { state: { skillName: item.name } });
  };

  const useWithAgent = (item: Capability, agentName: string) => {
    if (item.status !== 'available') {
      setNotice('这个能力当前不可用，请选择其他能力。');
      return;
    }
    ensureChosen(item.id);
    const matched = agents.find((agent) => agent.name === agentName);
    navigate('/copilot', {
      state: {
        skillName: item.name,
        agentId: matched?.id,
        agentName,
        agentExample: matched?.example ?? `请结合「${item.name}」帮我完成：${item.useCase}`,
      },
    });
  };

  const browseCapabilities = async () => {
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
        title="技能"
        description="从技能管理已发布并对工作区开放的能力中选用，加入后可配合关联智能体使用。"
        meta={
          <>
            <span>可浏览 {availableCount}</span>
            <span>技能 {chosenList.length}</span>
            <span>收藏 {favorites.length}</span>
            <span>最近使用 {recent.length}</span>
            {(isLoading || isFetching) && <span>同步中…</span>}
          </>
        }
        actions={
          <button
            ref={browseTriggerRef}
            type="button"
            onClick={() => { void browseCapabilities(); }}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]"
          >
            <Sparkles className="h-3.5 w-3.5" />浏览能力
          </button>
        }
      />

      {notice && <NoticeBanner tone="violet" onClose={() => setNotice('')}>{notice}</NoticeBanner>}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_280px]">
        <section id="skills-catalog" aria-labelledby="skills-title" className="min-w-0 overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
          <h3 id="skills-title" className="sr-only">技能列表</h3>
          <CatalogToolbar
            search={params.q ?? ''}
            onSearch={(value) => setParams((current) => ({ ...current, q: value }))}
            searchLabel="搜索能力"
            placeholder="搜索 Skill、Tool、MCP 或智能体"
            filters={[
              {
                label: '类型',
                value: params.type ?? 'all',
                onChange: (value) => setParams((current) => ({ ...current, type: value as SkillListParams['type'] })),
                options: [
                  { value: 'all', label: '全部类型' },
                  { value: 'Skill', label: 'Skill' },
                  { value: 'Tool', label: 'Tool' },
                  { value: 'MCP', label: 'MCP' },
                ],
              },
              {
                label: '状态',
                value: params.status ?? 'all',
                onChange: (value) => setParams((current) => ({ ...current, status: value as SkillListParams['status'] })),
                options: [
                  { value: 'all', label: '全部状态' },
                  { value: 'available', label: '可使用' },
                  { value: 'unavailable', label: '暂不可用' },
                ],
              },
              {
                label: '收藏筛选',
                value: params.onlyFavorites ? 'favorites' : 'all',
                onChange: (value) => setParams((current) => ({ ...current, onlyFavorites: value === 'favorites' })),
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
              {visible.map((item) => {
                const meta = TYPE_META[item.type];
                const Icon = meta.icon;
                const fav = favorites.includes(item.id);
                return (
                  <article key={item.id} className="group flex min-h-[250px] flex-col rounded-2xl border border-[var(--border)] p-5 transition hover:border-[var(--brand)] hover:shadow-[var(--shadow-sm)]">
                    <div className="flex items-start justify-between">
                      <span className={`grid h-10 w-10 place-items-center rounded-xl ${meta.tone}`}><Icon className="h-5 w-5" /></span>
                      <button
                        type="button"
                        aria-label={`${fav ? '取消收藏' : '收藏'}${item.name}`}
                        aria-pressed={fav}
                        onClick={() => toggleFavorite(item)}
                        className={`rounded-lg p-2 ${fav ? 'text-rose-500' : 'text-[var(--text-muted)] hover:text-rose-500'}`}
                      >
                        <Heart className="h-4 w-4" fill={fav ? 'currentColor' : 'none'} />
                      </button>
                    </div>
                    <button type="button" onClick={() => setSelected(item)} className="mt-4 text-left">
                      <span className="text-[10px] font-semibold text-[var(--text-muted)]">{item.type} · {meta.label}</span>
                      <h4 className="mt-2 text-base font-semibold leading-6 group-hover:text-[var(--brand)]">{item.name}</h4>
                      <p className="mt-2 line-clamp-2 text-xs leading-6 text-[var(--text-muted)]">{item.description}</p>
                    </button>
                    {item.relatedAgents.length > 0 ? (
                      <p className="mt-3 flex items-center gap-1 truncate text-[11px] text-[var(--text-muted)]">
                        <Bot className="h-3 w-3 shrink-0" />
                        关联 {item.relatedAgents.slice(0, 2).join('、')}
                        {item.relatedAgents.length > 2 ? ` 等${item.relatedAgents.length}个` : ''}
                      </p>
                    ) : (
                      <p className="mt-3 truncate text-[11px] text-[var(--text-muted)]">{item.owner}</p>
                    )}
                    <div className="mt-2 flex items-center justify-between gap-2 text-[11px] text-[var(--text-muted)]">
                      <span className="truncate">{item.owner}</span>
                      <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${item.status === 'available' ? 'bg-[var(--success-bg)] text-[var(--success)]' : 'bg-[var(--bg-hover)] text-[var(--text-muted)]'}`}>
                        {item.status === 'available' ? '可使用' : '暂不可用'}
                      </span>
                    </div>
                    <CardActions>
                      <CardActionButton aria-label={`移出${item.name}`} onClick={() => toggleChosen(item.id)}>移出</CardActionButton>
                      <CardActionButton onClick={() => setSelected(item)}>了解详情</CardActionButton>
                      <CardActionButton tone="brand" disabled={item.status !== 'available'} onClick={() => (item.type === 'Tool' ? useToolInCopilot(item) : openUse(item))}>
                        开始使用
                      </CardActionButton>
                    </CardActions>
                  </article>
                );
              })}
            </div>
          ) : (
            <EmptyFilterState
              title={chosenList.length === 0 ? (list.length === 0 ? '管理员尚未开放能力' : '还没有技能') : '没有匹配的能力'}
              description={
                chosenList.length === 0
                  ? (list.length === 0
                    ? '请在技能管理中发布并对工作区开放后再来选用。'
                    : '点击「浏览能力」，从技能管理已开放的条目中加入技能。')
                  : '尝试其他关键词或清除筛选。'
              }
              action={
                chosenList.length === 0 && list.length > 0 ? (
                  <button type="button" onClick={() => { void browseCapabilities(); }} className="text-xs font-semibold text-[var(--brand)] hover:underline">
                    去浏览能力
                  </button>
                ) : chosenList.length > 0 ? (
                  <button type="button" onClick={() => setParams(DEFAULT_PARAMS)} className="text-xs font-semibold text-[var(--brand)] hover:underline">
                    清除筛选
                  </button>
                ) : null
              }
            />
          )}
          {isLoading && !list.length && <p className="px-5 pb-5 text-xs text-[var(--text-muted)]">加载中…</p>}
        </section>

        <aside className="space-y-5">
          <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <Clock3 className="h-4 w-4 text-[var(--brand)]" />最近使用
            </div>
            <p className="mt-2 text-xs text-[var(--text-muted)]">最近带入工作的能力。</p>
            {recent.length === 0 ? (
              <p className="mt-5 text-xs leading-6 text-[var(--text-muted)]">加入并使用后，会显示在这里。</p>
            ) : (
            <ol className="mt-5 space-y-3">
              {recent.map((item) => (
                <li key={item.id} className="flex items-center gap-3">
                  <span className="grid h-8 w-8 place-items-center rounded-lg bg-[var(--bg-elevated)] text-[var(--brand)]">
                    <Sparkles className="h-4 w-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-xs font-semibold">{item.name}</span>
                    <span className="mt-1 block text-[10px] text-[var(--text-muted)]">{item.type} · {item.time}</span>
                  </span>
                </li>
              ))}
            </ol>
            )}
          </section>
        </aside>
      </div>

      <BrowseCapabilitiesDrawer
        open={browseOpen}
        capabilities={list}
        chosenIds={chosenIds}
        loading={isLoading || isFetching}
        onClose={closeBrowse}
        onToggleChosen={toggleChosen}
        onUse={openUse}
        onUseWithAgent={useWithAgent}
      />

      <CapabilityDrawer
        selected={selected}
        onClose={() => setSelected(null)}
        favorited={selected ? favorites.includes(selected.id) : false}
        onToggleFavorite={toggleFavorite}
        onUse={openUse}
        onUseInCopilot={useToolInCopilot}
        onUseWithAgent={useWithAgent}
      />
      <UseModal target={useTarget} onClose={() => setUseTarget(null)} onConfirm={confirmUse} />
    </WorkspacePage>
  );
}
