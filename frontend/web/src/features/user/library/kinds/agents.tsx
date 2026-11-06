/**
 * **智能体** ✓ —— 资源库的「智能体」页签 ✓。
 *
 * ⚠️ **原始类型留在这一层** ✓ —— 投影成 :class:`ResourceItem` 交给通用骨架 ✓
 * （骨架只画 ✓ —— 动作在这里 ✓）。
 */

import { Bot, FileText, MessageSquareText, ShieldCheck, Sparkles, UsersRound } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { qk } from '@/api/shared/query-keys';
import { withDefaults } from '@/api/shared/pagination';
import { runtimeStorageKey } from '@/lib/environment';
import { useApiMutation, useApiQuery } from '@/services/query';

import { PageIntro } from '../../components';
import { applyFavorite } from '../../favoriteState';
import { ResourceBrowserDrawer, ResourceDetailDrawer } from '../ResourceDrawers';
import { ResourceSection } from '../ResourceSection';
import type { ResourceCopy, ResourceItem } from '../schema';

export type AgentCategory = '销售支持' | '企业通用' | '客服应答' | '数据分析' | '文案创作';

export interface Agent {
  id: string;
  name: string;
  description: string;
  category: AgentCategory;
  owner: string;
  useCase: string;
  input: string;
  output: string;
  example: string;
  /** icon 由 category 在页面侧映射,这里不存组件引用 */
  tone: string;
}

export interface AgentListParams {
  q?: string;
  category?: 'all' | AgentCategory;
  onlyFavorites?: boolean;
}

export interface ToggleFavoriteVars {
  id: string;
  on: boolean;
}

const PATH = '/api/catalog/agents';
const CHOSEN_STORAGE_KEY = runtimeStorageKey('user.agents.chosen');

const ICON_BY_CATEGORY: Record<AgentCategory, typeof UsersRound> = {
  销售支持: UsersRound,
  企业通用: FileText,
  客服应答: ShieldCheck,
  数据分析: Bot,
  文案创作: Sparkles,
};

const CATEGORY_LABEL: Record<'all' | AgentCategory, string> = {
  all: '全部场景',
  销售支持: '销售支持',
  企业通用: '企业通用',
  客服应答: '客服应答',
  数据分析: '数据分析',
  文案创作: '文案创作',
};

const COPY: ResourceCopy = {
  eyebrow: '智能体详情',
  browseTitle: '浏览并选用',
  browseDescription:
    '以下为管理员已发布并对工作区开放的智能体。勾选加入「已选用」，或直接开始对话。',
  chosenHint: '勾选后会出现在智能体页签',
  emptyTitle: '管理员尚未开放智能体',
  emptyDescription: '请在智能体管理中发布并开放给工作区后再来选用。',
};

export function useAgents(params: AgentListParams = {}) {
  const query = withDefaults(params);
  return useApiQuery<Agent[]>(
    [...qk.user.agents.list],
    PATH,
    { query },
    { staleTime: 15_000, placeholderData: (prev) => prev },
  );
}

export function useToggleAgentFavorite() {
  return useApiMutation<Agent, ToggleFavoriteVars>(
    (vars) => `${PATH}/${vars.id}/favorite`,
    { invalidateKeys: [qk.user.agents.root] },
    'POST',
  );
}

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

function toResource(agent: Agent, run: () => void): ResourceItem {
  const Icon = ICON_BY_CATEGORY[agent.category] ?? Bot;
  return {
    id: agent.id,
    name: agent.name,
    description: agent.description,
    meta: `${agent.category} · ${agent.owner}`,
    filters: { 场景: agent.category },
    tone: agent.tone,
    icon: Icon,
    fields: [
      { label: '适合处理', value: agent.useCase },
      { label: '预期产出', value: agent.output },
    ],
    note: `${agent.input}。生成内容仅供参考，重要结果需人工核对；涉及外部发送或数据修改时应先确认。`,
    primary: { label: '开始对话', ariaLabel: `与${agent.name}开始对话`, icon: MessageSquareText, run },
  };
}

export function AgentsKind() {
  const navigate = useNavigate();
  const { data: list = [], isLoading, isFetching, isError, error } = useAgents();
  const favoriteMutation = useToggleAgentFavorite();

  const [favorites, setFavorites] = useState<string[]>([]);
  const [chosenIds, setChosenIds] = useState<string[]>(() => readChosenIds());
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState<'all' | AgentCategory>('all');
  const [onlyFavorites, setOnlyFavorites] = useState(false);
  const [selected, setSelected] = useState<Agent | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  const [browseOpen, setBrowseOpen] = useState(false);

  useEffect(() => {
    sessionStorage.setItem(CHOSEN_STORAGE_KEY, JSON.stringify(chosenIds));
  }, [chosenIds]);

  // 目录里已下线的选用项自动清理
  useEffect(() => {
    if (list.length === 0) return;
    const openIds = new Set(list.map((agent) => agent.id));
    setChosenIds((current) => {
      const next = current.filter((id) => openIds.has(id));
      return next.length === current.length ? current : next;
    });
  }, [list]);

  const startConversation = (agent: Agent) => {
    if (!chosenIds.includes(agent.id)) {
      setChosenIds((current) => [...current, agent.id]);
    }
    navigate('/copilot', {
      state: { agentId: agent.id, agentName: agent.name, agentExample: agent.example },
    });
  };

  const toggleChosen = (id: string) =>
    setChosenIds((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );

  const toggleFavorite = (id: string) => {
    const on = !favorites.includes(id);
    favoriteMutation
      .mutateAsync({ id, on })
      .then(() => setFavorites((current) => applyFavorite(current, id, on)))
      .catch((cause) => window.alert(`收藏失败：${String(cause)}`));
  };

  const chosenAgents = useMemo(
    () => list.filter((agent) => chosenIds.includes(agent.id)),
    [list, chosenIds],
  );

  const categoryOptions = useMemo(() => {
    const present = Array.from(new Set(chosenAgents.map((agent) => agent.category))) as AgentCategory[];
    return ['all', ...present] as Array<'all' | AgentCategory>;
  }, [chosenAgents]);

  // ⚠️ **浏览抽屉的筛选选项取全量** ✓ —— 目录里还没选过的也要能筛出来 ✓
  // （只给「已选中的类别」的话 ✓ → 第一次打开就只有一个「全部」✓ → 筛不了 ✗✗）。
  const browseCategoryOptions = useMemo(() => {
    const present = Array.from(new Set(list.map((agent) => agent.category))) as AgentCategory[];
    return ['all', ...present] as Array<'all' | AgentCategory>;
  }, [list]);

  const visible = useMemo(
    () =>
      chosenAgents.filter(
        (agent) =>
          (category === 'all' || agent.category === category) &&
          (!onlyFavorites || favorites.includes(agent.id)) &&
          `${agent.name} ${agent.description} ${agent.category} ${agent.owner}`
            .toLowerCase()
            .includes(query.trim().toLowerCase()),
      ),
    [chosenAgents, category, onlyFavorites, favorites, query],
  );

  const allResources = useMemo(
    () => list.map((agent) => toResource(agent, () => startConversation(agent))),
    [list, chosenIds],
  );
  const visibleResources = useMemo(
    () =>
      visible.map((agent) => toResource(agent, () => startConversation(agent))),
    [visible, chosenIds],
  );

  const resetFilters = () => {
    setQuery('');
    setCategory('all');
    setOnlyFavorites(false);
  };

  return (
    <>
      <PageIntro
        title="智能体"
        description="从管理员已发布的智能体中选用，进入对话完成工作。"
        meta={
          <>
            <span>开放 {list.length}</span>
            <span>已选用 {chosenAgents.length}</span>
            <span>收藏 {favorites.length}</span>
            {(isLoading || isFetching) && <span>同步中…</span>}
          </>
        }
        actions={
          <button
            type="button"
            onClick={() => setBrowseOpen(true)}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]"
          >
            <MessageSquareText className="h-3.5 w-3.5" />浏览并选用
          </button>
        }
      />
      {isError && (
        <p role="alert" className="rounded-xl border border-rose-300 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          加载失败：{String(error)}
        </p>
      )}

      <ResourceSection
        items={visibleResources}
        query={query}
        onQuery={setQuery}
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
        countLabel={`${visibleResources.length} 项`}
        favorited={favorites}
        onToggleFavorite={toggleFavorite}
        onOpenDetails={(item, trigger) => {
          triggerRef.current = trigger;
          setSelected(list.find((agent) => agent.id === item.id) ?? null);
        }}
        chosen={chosenIds}
        onToggleChosen={toggleChosen}
        detailsLabel="了解详情"
        loading={isLoading || isFetching}
        empty={{
          title:
            chosenAgents.length === 0
              ? list.length === 0
                ? COPY.emptyTitle
                : '还没有选用智能体'
              : '没有找到符合条件的智能体',
          description:
            chosenAgents.length === 0
              ? list.length === 0
                ? COPY.emptyDescription
                : '点击右上角「浏览并选用」，从开放目录中勾选需要的助手。'
              : '试试其他关键词，或清除筛选后重新查看。',
          action:
            chosenAgents.length === 0 && list.length > 0 ? (
              <button
                type="button"
                onClick={() => setBrowseOpen(true)}
                className="text-xs font-semibold text-[var(--brand)] hover:underline"
              >
                去浏览并选用
              </button>
            ) : chosenAgents.length > 0 ? (
              <button
                type="button"
                onClick={resetFilters}
                className="text-xs font-semibold text-[var(--brand)] hover:underline"
              >
                清除筛选
              </button>
            ) : null,
        }}
      />

      <ResourceDetailDrawer
        item={selected ? toResource(selected, () => startConversation(selected)) : null}
        onClose={() => setSelected(null)}
        copy={COPY}
        favorited={selected ? favorites.includes(selected.id) : false}
        onToggleFavorite={() => selected && toggleFavorite(selected.id)}
        chosen={selected ? chosenIds.includes(selected.id) : false}
        onToggleChosen={() => selected && toggleChosen(selected.id)}
        restoreFocusTo={triggerRef.current}
        onPrimary={() => selected && startConversation(selected)}
      />

      <ResourceBrowserDrawer
        open={browseOpen}
        onClose={() => setBrowseOpen(false)}
        items={allResources}
        chosen={chosenIds}
        onToggleChosen={toggleChosen}
        onPrimary={(item) => {
          const agent = list.find((row) => row.id === item.id);
          if (agent) startConversation(agent);
        }}
        loading={isLoading || isFetching}
        copy={COPY}
        searchPlaceholder="搜索名称、场景或团队"
        filters={[
          {
            label: '场景',
            options: browseCategoryOptions.map((item) => ({
              value: item,
              label: CATEGORY_LABEL[item] ?? item,
            })),
          },
        ]}
      />
    </>
  );
}
