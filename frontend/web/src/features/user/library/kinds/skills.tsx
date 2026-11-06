/**
 * **技能** ✓ —— 资源库的「技能」页签 ✓（Skill / Tool / MCP 三类能力 ✓）。
 */

import { Bot, Clock3, Network, Sparkles, Wrench } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { qk } from '@/api/shared/query-keys';
import { withDefaults } from '@/api/shared/pagination';
import { runtimeStorageKey } from '@/lib/environment';
import { useApiMutation, useApiQuery } from '@/services/query';

import { CenterModal } from '@/components/feedback/CenterModal';
import { NoticeBanner } from '@/components/feedback/NoticeBanner';

import { PageIntro } from '../../components';
import { applyFavorite } from '../../favoriteState';
import { ResourceBrowserDrawer, ResourceDetailDrawer } from '../ResourceDrawers';
import { ResourceSection } from '../ResourceSection';
import type { ResourceCopy, ResourceItem } from '../schema';
import { useAgents } from './agents';

export type CapabilityType = 'Skill' | 'Tool' | 'MCP';
export type CapabilityStatus = 'available' | 'unavailable';
export type CapabilityRisk = 'low' | 'needsConfirm';

export interface Capability {
  id: string;
  name: string;
  type: CapabilityType;
  description: string;
  owner: string;
  useCase: string;
  input: string;
  output: string;
  risk: CapabilityRisk;
  status: CapabilityStatus;
  tags: string[];
  lastUsed: string;
  /** 管理端 usedByAgents：已绑定该能力的智能体名称 */
  relatedAgents: string[];
}

export interface SkillListParams {
  type?: 'all' | CapabilityType;
  status?: 'all' | CapabilityStatus;
  q?: string;
  onlyFavorites?: boolean;
}

export interface ToggleFavoriteVars {
  id: string;
  on: boolean;
}

export interface RecordUseVars {
  id: string;
  goal: string;
}

interface RecentUseItem {
  id: string;
  name: string;
  type: CapabilityType;
  time: string;
}

const PATH = '/api/catalog/skills';
const CHOSEN_STORAGE_KEY = runtimeStorageKey('user.skills.chosen');

const TYPE_META = {
  Skill: { icon: Sparkles, tone: 'bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300', label: '工作技能' },
  Tool: { icon: Wrench, tone: 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300', label: '受控工具' },
  MCP: { icon: Network, tone: 'bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300', label: '外部连接' },
} as const;

const COPY: ResourceCopy = {
  eyebrow: '能力详情',
  browseTitle: '浏览能力',
  browseDescription: '以下为管理员已对工作区开放的能力。勾选加入「已选用」，或直接开始使用。',
  chosenHint: '勾选后会出现在技能页签',
  emptyTitle: '管理员尚未开放能力',
  emptyDescription: '请在技能管理中发布并对工作区开放后再来选用。',
};

export function useCapabilities(params: SkillListParams = {}) {
  const query = withDefaults(params);
  return useApiQuery<Capability[]>(
    [...qk.user.skills.list],
    PATH,
    { query },
    { staleTime: 15_000, placeholderData: (prev) => prev },
  );
}

export function useToggleFavorite() {
  return useApiMutation<Capability, ToggleFavoriteVars>(
    (vars) => `${PATH}/${vars.id}/favorite`,
    { invalidateKeys: [qk.user.skills.root] },
    'POST',
  );
}

export function useRecordUse() {
  return useApiMutation<{ id: string; recordedAt: string }, RecordUseVars>(
    (vars) => `${PATH}/${vars.id}/record-use`,
    { invalidateKeys: [qk.user.skills.recent, qk.user.skills.root] },
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

export function SkillsKind() {
  const navigate = useNavigate();
  const { data: list = [], isLoading, isFetching, isError, error } = useCapabilities();
  const { data: agents = [] } = useAgents();
  const toggleFav = useToggleFavorite();
  const recordUse = useRecordUse();

  const [params, setParams] = useState<SkillListParams>({ type: 'all', q: '' });
  const [favorites, setFavorites] = useState<string[]>([]);
  const [chosenIds, setChosenIds] = useState<string[]>(() => readChosenIds());
  const [browseOpen, setBrowseOpen] = useState(false);
  const [selected, setSelected] = useState<Capability | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  const [useTarget, setUseTarget] = useState<Capability | null>(null);
  const [recent, setRecent] = useState<RecentUseItem[]>([]);
  const [notice, setNotice] = useState('');
  const [goal, setGoal] = useState('');

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

  const toggleChosen = (id: string) =>
    setChosenIds((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );

  const ensureChosen = (id: string) =>
    setChosenIds((current) => (current.includes(id) ? current : [...current, id]));

  const toggleFavorite = (item: Capability) => {
    const on = !favorites.includes(item.id);
    toggleFav
      .mutateAsync({ id: item.id, on })
      .then(() => setFavorites((current) => applyFavorite(current, item.id, on)))
      .catch((cause) => setNotice(`收藏失败：${String(cause)}`));
  };

  const openUse = (item: Capability) => {
    if (item.status !== 'available') {
      setNotice('这个能力当前不可用，请选择其他能力。');
      return;
    }
    ensureChosen(item.id);
    setUseTarget(item);
  };

  const confirmUse = () => {
    if (!useTarget) return;
    recordUse.mutate(
      { id: useTarget.id, goal },
      {
        onSuccess: (result) => {
          setRecent((current) =>
            [
              { id: result.id, name: useTarget.name, type: useTarget.type, time: result.recordedAt },
              ...current,
            ].slice(0, 5),
          );
          setNotice(`「${useTarget.name}」使用记录已保存。`);
          setUseTarget(null);
          setGoal('');
          setBrowseOpen(false);
        },
        onError: (cause) => setNotice(`使用失败：${String(cause)}`),
      },
    );
  };

  const useInCopilot = (item: Capability) => {
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

  const chosenList = useMemo(
    () => list.filter((item) => chosenIds.includes(item.id)),
    [list, chosenIds],
  );

  const visible = useMemo(() => {
    const q = params.q?.trim().toLowerCase() ?? '';
    return chosenList.filter(
      (item) =>
        (params.type === 'all' || params.type === undefined || item.type === params.type) &&
        (params.status === 'all' || params.status === undefined || item.status === params.status) &&
        (!params.onlyFavorites || favorites.includes(item.id)) &&
        `${item.name} ${item.description} ${item.owner} ${item.tags.join(' ')} ${item.relatedAgents.join(' ')}`
          .toLowerCase()
          .includes(q),
    );
  }, [chosenList, params, favorites]);

  const toResource = (item: Capability): ResourceItem => ({
    id: item.id,
    name: item.name,
    description: item.description,
    meta: `${item.type} · ${item.owner}`,
    filters: { 类型: item.type, 状态: item.status },
    tone: TYPE_META[item.type].tone,
    icon: TYPE_META[item.type].icon,
    badge: {
      label: item.status === 'available' ? '可使用' : '暂不可用',
      tone: item.status === 'available' ? 'ok' : 'muted',
    },
    fields: [
      { label: '类型', value: TYPE_META[item.type].label },
      { label: '风险', value: item.risk === 'low' ? '低风险' : '需确认' },
      { label: '输入', value: item.input },
      { label: '输出', value: item.output },
      { label: '标签', value: item.tags.join('、') || '—' },
      { label: '最近使用', value: item.lastUsed || '—' },
    ],
    extra:
      item.relatedAgents.length > 0 ? (
        <div className="rounded-xl border border-[var(--border)] p-4">
          <p className="text-xs font-semibold">关联智能体</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {item.relatedAgents.map((agentName) => (
              <button
                key={agentName}
                type="button"
                disabled={item.status !== 'available'}
                aria-label={`用${agentName}使用${item.name}`}
                onClick={() => useWithAgent(item, agentName)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs font-medium hover:border-[var(--brand)] hover:text-[var(--brand)] disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Bot className="h-3.5 w-3.5" />
                {agentName}
              </button>
            ))}
          </div>
        </div>
      ) : undefined,
    primary: {
      label: '开始使用',
      disabled: item.status !== 'available',
      run: () => (item.type === 'Tool' ? useInCopilot(item) : openUse(item)),
    },
  });

  const allResources = useMemo(() => list.map(toResource), [list, agents, chosenIds]);
  const visibleResources = useMemo(() => visible.map(toResource), [visible, agents, chosenIds]);

  const resetFilters = () => setParams({ type: 'all', q: '' });

  return (
    <>
      <PageIntro
        title="技能"
        description="Skill / Tool / MCP 三类能力，选中后即可在对话中使用。"
        meta={
          <>
            <span>开放 {list.length}</span>
            <span>已选用 {chosenList.length}</span>
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
            <Sparkles className="h-3.5 w-3.5" />浏览能力
          </button>
        }
      />
      {isError && (
        <p role="alert" className="rounded-xl border border-rose-300 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          加载失败：{String(error)}
        </p>
      )}
      {notice ? (
        <NoticeBanner tone="sky" onClose={() => setNotice('')}>
          {notice}
        </NoticeBanner>
      ) : null}

      <ResourceSection
        items={visibleResources}
        query={params.q ?? ''}
        onQuery={(value) => setParams((current) => ({ ...current, q: value }))}
        searchLabel="搜索技能"
        placeholder="搜索技能、描述或负责人"
        filters={[
          {
            label: '类型',
            value: params.type ?? 'all',
            onChange: (value) => setParams((current) => ({ ...current, type: value as SkillListParams['type'] })),
            options: [
              { value: 'all', label: '全部类型' },
              { value: 'Skill', label: '工作技能' },
              { value: 'Tool', label: '受控工具' },
              { value: 'MCP', label: '外部连接' },
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
        ]}
        countLabel={`${visibleResources.length} 项`}
        favorited={favorites}
        onToggleFavorite={(id) => {
          const item = list.find((row) => row.id === id);
          if (item) toggleFavorite(item);
        }}
        onOpenDetails={(item, trigger) => {
          triggerRef.current = trigger;
          setSelected(list.find((row) => row.id === item.id) ?? null);
        }}
        chosen={chosenIds}
        onToggleChosen={toggleChosen}
        detailsLabel="了解详情"
        loading={isLoading || isFetching}
        empty={{
          title:
            chosenList.length === 0
              ? list.length === 0
                ? COPY.emptyTitle
                : '还没有技能'
              : '没有匹配的能力',
          description:
            chosenList.length === 0
              ? list.length === 0
                ? COPY.emptyDescription
                : '点击「浏览能力」，从技能管理已开放的条目中加入技能。'
              : '尝试其他关键词或清除筛选。',
          action:
            chosenList.length === 0 && list.length > 0 ? (
              <button
                type="button"
                onClick={() => setBrowseOpen(true)}
                className="text-xs font-semibold text-[var(--brand)] hover:underline"
              >
                去浏览能力
              </button>
            ) : chosenList.length > 0 ? (
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

      {recent.length ? (
        <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <Clock3 className="h-4 w-4 text-[var(--brand)]" />最近使用
          </h2>
          <ol className="mt-4 space-y-2">
            {recent.map((item) => (
              <li key={item.id} className="flex items-center gap-3">
                <span className="grid h-8 w-8 place-items-center rounded-lg bg-[var(--bg-elevated)] text-[var(--brand)]">
                  <Sparkles className="h-4 w-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-semibold">{item.name}</span>
                  <span className="mt-1 block text-[10px] text-[var(--text-muted)]">
                    {item.type} · {item.time}
                  </span>
                </span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      <ResourceDetailDrawer
        item={selected ? toResource(selected) : null}
        onClose={() => setSelected(null)}
        copy={COPY}
        favorited={selected ? favorites.includes(selected.id) : false}
        onToggleFavorite={() => selected && toggleFavorite(selected)}
        chosen={selected ? chosenIds.includes(selected.id) : false}
        onToggleChosen={() => selected && toggleChosen(selected.id)}
        restoreFocusTo={triggerRef.current}
        onPrimary={() => {
          if (!selected) return;
          if (selected.type === 'Tool') useInCopilot(selected);
          else openUse(selected);
        }}
      />

      <ResourceBrowserDrawer
        open={browseOpen}
        onClose={() => setBrowseOpen(false)}
        items={allResources}
        chosen={chosenIds}
        onToggleChosen={toggleChosen}
        onPrimary={(item) => {
          const capability = list.find((row) => row.id === item.id);
          if (!capability) return;
          if (capability.type === 'Tool') useInCopilot(capability);
          else openUse(capability);
        }}
        loading={isLoading || isFetching}
        copy={COPY}
        searchPlaceholder="搜索能力、描述或负责人"
        filters={[
          {
            label: '类型',
            options: [
              { value: 'all', label: '全部类型' },
              { value: 'Skill', label: '工作技能' },
              { value: 'Tool', label: '受控工具' },
              { value: 'MCP', label: '外部连接' },
            ],
          },
        ]}
      />

      <CenterModal
        open={useTarget !== null}
        onClose={() => {
          setGoal('');
          setUseTarget(null);
        }}
        ariaLabel={useTarget ? `使用${useTarget.name}` : '使用能力'}
        title={useTarget ? `使用能力：${useTarget.name}` : '使用能力'}
        description="填写这次使用的目标，确认后会记录到最近使用，不会触发真实执行。"
        closeLabel="关闭使用能力窗口"
        onSubmit={(event) => {
          event.preventDefault();
          confirmUse();
        }}
        footer={
          <>
            <button
              type="button"
              onClick={() => {
                setGoal('');
                setUseTarget(null);
              }}
              className="rounded-xl border border-[var(--border)] px-4 py-2.5 text-sm font-medium"
            >
              取消
            </button>
            <button
              type="submit"
              className="rounded-xl bg-[var(--brand)] px-4 py-2.5 text-sm font-semibold text-white"
            >
              确认使用
            </button>
          </>
        }
      >
        <label className="mt-6 block text-xs font-semibold">
          本次任务目标
          <textarea
            autoFocus
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
            required
            placeholder="例如：整理本周客户反馈并提取三个行动项"
            className="mt-2 min-h-24 w-full resize-y rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] p-3 text-sm font-normal outline-none focus:border-[var(--brand)]"
          />
        </label>
      </CenterModal>
    </>
  );
}
