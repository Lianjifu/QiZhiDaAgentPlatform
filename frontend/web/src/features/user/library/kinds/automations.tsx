/**
 * **工作流** ✓ —— 资源库的「工作流」页签 ✓。
 */

import { Activity, CirclePlay, Workflow } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';

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

export type FlowAvailability = 'available' | 'unavailable';

export interface Flow {
  id: string;
  name: string;
  scene: string;
  description: string;
  owner: string;
  cadence: string;
  availability: FlowAvailability;
  steps: string[];
  lastRun: string;
  usage: number;
}

export interface FlowRun {
  id: string;
  name: string;
  time: string;
  result: string;
  /** ⚠️ **执行结论** ✓ —— 工作流是真的跑了一遍 ✓（不是「记一条使用记录」✓）。 */
  ok?: boolean;
  /** 每一步的执行明细 ✓（节点 / 类别 / 输出 ✓）。 */
  steps?: { nodeId: string; kind: string; label: string; ok: boolean; error?: string }[];
  summary?: string;
  error?: string;
}

export interface FlowListParams {
  q?: string;
  scene?: 'all' | string;
  availability?: 'all' | FlowAvailability;
}

export interface ToggleFavoriteVars {
  id: string;
  on: boolean;
}

export interface RecordRunVars {
  flowId: string;
  note?: string;
}

const PATH = '/api/catalog/workflows';
const CHOSEN_STORAGE_KEY = runtimeStorageKey('user.automations.chosen');

const COPY: ResourceCopy = {
  eyebrow: '工作流详情',
  detailSuffix: '工作流详情',
  browseTitle: '浏览工作流',
  browseDescription: '以下为管理员已发布的工作流。勾选加入「已选用」，或直接运行。',
  chosenHint: '勾选后会出现在工作流页签',
  emptyTitle: '管理员尚未发布工作流',
  emptyDescription: '请在工作流管理中发布流程后再来选用。',
};

export function useFlows(params: FlowListParams = {}) {
  const query = withDefaults(params);
  return useApiQuery<Flow[]>(
    [...qk.user.automations.list],
    PATH,
    { query },
    { staleTime: 15_000, placeholderData: (prev) => prev },
  );
}

export function useFlowRuns() {
  return useApiQuery<FlowRun[]>(
    [...qk.user.automations.runs],
    `${PATH}/__runs__`,
    undefined,
    { staleTime: 15_000 },
  );
}

export function useToggleFlowFavorite() {
  return useApiMutation<Flow, ToggleFavoriteVars>(
    (vars) => `${PATH}/${vars.id}/favorite`,
    { invalidateKeys: [qk.user.automations.root] },
    'POST',
  );
}

export function useRecordFlowRun() {
  return useApiMutation<FlowRun, RecordRunVars>(
    (vars) => `${PATH}/${vars.flowId}/run`,
    { invalidateKeys: [qk.user.automations.runs, qk.user.automations.root] },
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

export function AutomationsKind() {
  const { data: list = [], isLoading, isFetching, isError, error } = useFlows();
  const { data: runs = [] } = useFlowRuns();
  const toggleFlowFavorite = useToggleFlowFavorite();
  const recordRun = useRecordFlowRun();

  const [query, setQuery] = useState('');
  const [scene, setScene] = useState('全部场景');
  const [availability, setAvailability] = useState<'all' | FlowAvailability>('all');
  const [favorites, setFavorites] = useState<string[]>([]);
  const [chosenIds, setChosenIds] = useState<string[]>(() => readChosenIds());
  const [browseOpen, setBrowseOpen] = useState(false);
  const [selected, setSelected] = useState<Flow | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  const [runTarget, setRunTarget] = useState<Flow | null>(null);
  const [runNote, setRunNote] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    sessionStorage.setItem(CHOSEN_STORAGE_KEY, JSON.stringify(chosenIds));
  }, [chosenIds]);

  useEffect(() => {
    if (list.length === 0) return;
    const openIds = new Set(list.map((flow) => flow.id));
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

  const toggleFavorite = (flow: Flow) => {
    const on = !favorites.includes(flow.id);
    toggleFlowFavorite
      .mutateAsync({ id: flow.id, on })
      .then(() => setFavorites((current) => applyFavorite(current, flow.id, on)))
      .catch((cause) => setNotice(`收藏失败：${String(cause)}`));
  };

  const openUse = (flow: Flow) => {
    if (flow.availability !== 'available') {
      setNotice('这个流程当前不可用，请选择其他可用流程。');
      return;
    }
    ensureChosen(flow.id);
    setRunTarget(flow);
  };

  const runFlow = () => {
    if (!runTarget || runTarget.availability !== 'available') return;
    ensureChosen(runTarget.id);
    recordRun.mutate(
      { flowId: runTarget.id, note: runNote },
      {
        onSuccess: (next) => {
          setNotice(
            `「${runTarget.name}」${next.ok === false ? '执行失败' : '执行完成'}：${next.summary || next.result}`,
          );
          setRunNote('');
          setRunTarget(null);
          setBrowseOpen(false);
        },
        onError: (cause) => setNotice(`执行失败：${String(cause)}`),
      },
    );
  };

  const chosenList = useMemo(
    () => list.filter((flow) => chosenIds.includes(flow.id)),
    [list, chosenIds],
  );

  const scenes = useMemo(
    () => ['全部场景', ...Array.from(new Set(chosenList.map((flow) => flow.scene)))],
    [chosenList],
  );

  const visible = useMemo(
    () =>
      chosenList.filter(
        (flow) =>
          (scene === '全部场景' || flow.scene === scene) &&
          (availability === 'all' || flow.availability === availability) &&
          `${flow.name} ${flow.description} ${flow.owner} ${flow.scene}`
            .toLowerCase()
            .includes(query.trim().toLowerCase()),
      ),
    [chosenList, scene, availability, query],
  );

  const toResource = (flow: Flow): ResourceItem => ({
    id: flow.id,
    name: flow.name,
    description: flow.description,
    meta: `${flow.scene} · ${flow.owner}`,
    filters: { 场景: flow.scene, 可用性: flow.availability },
    tone: 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300',
    icon: Workflow,
    badge: {
      label: flow.availability === 'available' ? '可使用' : '暂不可用',
      tone: flow.availability === 'available' ? 'ok' : 'muted',
    },
    fields: [
      { label: '使用方式', value: flow.cadence },
      { label: '当前状态', value: flow.availability === 'available' ? '可使用' : '暂不可用' },
      { label: '最近运行', value: flow.lastRun || '—' },
      { label: '累计使用', value: `${flow.usage} 次` },
      { label: '执行步骤', value: flow.steps.join(' → ') || '—' },
    ],
    primary: {
      label: '运行',
      icon: CirclePlay,
      disabled: flow.availability !== 'available',
      run: () => openUse(flow),
    },
  });

  const allResources = useMemo(() => list.map(toResource), [list, chosenIds]);
  const visibleResources = useMemo(() => visible.map(toResource), [visible, chosenIds]);

  const resetFilters = () => {
    setQuery('');
    setAvailability('all');
    setScene('全部场景');
  };

  return (
    <>
      <PageIntro
        title="工作流"
        description="管理员发布的流程，选中后可直接运行。"
        meta={
          <>
            <span>开放 {list.length}</span>
            <span>已选用 {chosenList.length}</span>
            <span>收藏 {favorites.length}</span>
            <span>最近使用 {runs.length}</span>
            {(isLoading || isFetching) && <span>同步中…</span>}
          </>
        }
        actions={
          <button
            type="button"
            onClick={() => setBrowseOpen(true)}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]"
          >
            <Workflow className="h-3.5 w-3.5" />浏览工作流
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
        query={query}
        onQuery={setQuery}
        searchLabel="搜索工作流"
        placeholder="搜索工作流、场景或团队"
        filters={[
          {
            label: '场景',
            value: scene,
            onChange: (value) => setScene(value),
            options: scenes.map((item) => ({ value: item, label: item })),
          },
          {
            label: '可用性',
            value: availability,
            onChange: (value) => setAvailability(value as 'all' | FlowAvailability),
            options: [
              { value: 'all', label: '全部' },
              { value: 'available', label: '可使用' },
              { value: 'unavailable', label: '暂不可用' },
            ],
          },
        ]}
        countLabel={`${visibleResources.length} 项`}
        favorited={favorites}
        onToggleFavorite={(id) => {
          const flow = list.find((row) => row.id === id);
          if (flow) toggleFavorite(flow);
        }}
        onOpenDetails={(item, trigger) => {
          triggerRef.current = trigger;
          setSelected(list.find((row) => row.id === item.id) ?? null);
        }}
        chosen={chosenIds}
        onToggleChosen={toggleChosen}
        detailsLabel="查看步骤"
        loading={isLoading || isFetching}
        empty={{
          title:
            chosenList.length === 0
              ? list.length === 0
                ? COPY.emptyTitle
                : '还没有工作流'
              : '没有匹配的工作流',
          description:
            chosenList.length === 0
              ? list.length === 0
                ? COPY.emptyDescription
                : '点击「浏览工作流」，从已发布目录中加入工作流。'
              : '尝试其他关键词、场景或可用性。',
          action:
            chosenList.length === 0 && list.length > 0 ? (
              <button
                type="button"
                onClick={() => setBrowseOpen(true)}
                className="text-xs font-semibold text-[var(--brand)] hover:underline"
              >
                去浏览工作流
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

      {runs.length ? (
        <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <Activity className="h-4 w-4 text-[var(--brand)]" />最近运行
          </h2>
          <ol className="mt-4 space-y-0">
            {runs.slice(0, 5).map((run) => (
              <li
                key={run.id}
                className="relative border-l border-[var(--border)] pb-5 pl-5 last:pb-0"
              >
                <span className="absolute -left-[5px] top-1.5 h-2.5 w-2.5 rounded-full bg-[var(--brand)] ring-4 ring-[var(--surface-1)]" />
                <p className="text-xs font-semibold">{run.name}</p>
                <p className="mt-1 text-[11px] text-[var(--text-muted)]">
                  {run.time} · {run.result}
                </p>
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
        onPrimary={() => selected && openUse(selected)}
      />

      <ResourceBrowserDrawer
        open={browseOpen}
        onClose={() => setBrowseOpen(false)}
        items={allResources}
        chosen={chosenIds}
        onToggleChosen={toggleChosen}
        onPrimary={(item) => {
          const flow = list.find((row) => row.id === item.id);
          if (flow) openUse(flow);
        }}
        loading={isLoading || isFetching}
        copy={COPY}
        searchPlaceholder="搜索流程、场景或负责人"
        filters={[
          {
            label: '场景',
            options: Array.from(new Set(list.map((flow) => flow.scene))).map((item) => ({
              value: item,
              label: item,
            })),
          },
        ]}
      />

      <CenterModal
        open={runTarget !== null}
        onClose={() => setRunTarget(null)}
        ariaLabel={runTarget ? `使用${runTarget.name}` : '使用工作流'}
        title={runTarget ? `使用工作流：${runTarget.name}` : '使用工作流'}
        description="确认后请求后端执行工作流。"
        closeLabel="关闭使用工作流窗口"
        onSubmit={(event) => {
          event.preventDefault();
          runFlow();
        }}
        footer={
          <>
            <button
              type="button"
              onClick={() => setRunTarget(null)}
              className="rounded-xl border border-[var(--border)] px-4 py-2.5 text-sm font-medium"
            >
              取消
            </button>
            <button
              type="submit"
              className="inline-flex items-center gap-2 rounded-xl bg-[var(--brand)] px-4 py-2.5 text-sm font-semibold text-white"
            >
              <CirclePlay className="h-4 w-4" />确认使用
            </button>
          </>
        }
      >
        <label className="mt-6 block text-xs font-semibold">
          给这次使用添加说明（可选）
          <textarea
            value={runNote}
            onChange={(event) => setRunNote(event.target.value)}
            placeholder="例如：整理本周华东客户进展"
            className="mt-2 min-h-24 w-full resize-y rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] p-3 text-sm font-normal outline-none focus:border-[var(--brand)]"
          />
        </label>
      </CenterModal>
    </>
  );
}
