/**
 * **知识** ✓ —— 资源库的「知识」页签 ✓（含问答区 ✓）。
 */

import { FileText, MessageCircleQuestion } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { NoticeBanner } from '@/components/feedback/NoticeBanner';
import { qk } from '@/api/shared/query-keys';
import { withDefaults } from '@/api/shared/pagination';
import { runtimeStorageKey } from '@/lib/environment';
import { useApiMutation, useApiQuery } from '@/services/query';

import { PageIntro } from '../../components';
import { applyFavorite } from '../../favoriteState';
import { ResourceBrowserDrawer, ResourceDetailDrawer } from '../ResourceDrawers';
import { ResourceSection } from '../ResourceSection';
import type { ResourceCopy, ResourceItem } from '../schema';

export type KnowledgeKind = '制度' | '项目' | '指南';
export type KnowledgeFilter = 'all' | KnowledgeKind | 'favorites';
export type KnowledgeSort = 'recent' | 'name';

export interface KnowledgeResource {
  id: string;
  title: string;
  kind: KnowledgeKind;
  description: string;
  owner: string;
  updated: string;
  tags: string[];
  excerpt: string;
  /** 后端返回的收藏状态（按用户）—— 刷新后据此恢复「已收藏」标记 */
  favorited?: boolean;
}

export interface KnowledgeListParams {
  q?: string;
  kind?: KnowledgeFilter;
  tag?: string;
  sort?: KnowledgeSort;
  onlyFavorites?: boolean;
}

export interface AskQuestionVars {
  question: string;
}

const PATH = '/api/catalog/knowledge';
const CHOSEN_STORAGE_KEY = runtimeStorageKey('user.knowledge.chosen');

const KIND_LABEL: Record<KnowledgeFilter, string> = {
  all: '全部类型',
  制度: '制度',
  项目: '项目',
  指南: '指南',
  favorites: '已收藏',
};

const COPY: ResourceCopy = {
  eyebrow: '知识详情',
  browseTitle: '浏览并选用',
  browseDescription: '以下为管理员已对工作区开放的知识条目。勾选加入「已选用」，或直接带入对话。',
  chosenHint: '勾选后会出现在知识页签',
  emptyTitle: '管理员尚未开放知识',
  emptyDescription: '请在知识管理中开放资料后再来选用。',
};

export function useKnowledgeResources(params: KnowledgeListParams = {}) {
  const query = withDefaults(params);
  return useApiQuery<KnowledgeResource[]>(
    [...qk.user.knowledge.list],
    PATH,
    { query },
    { staleTime: 15_000, placeholderData: (prev) => prev },
  );
}

export function useAskQuestion() {
  return useApiMutation<{ question: string; resourceId: string }, AskQuestionVars>(
    () => `${PATH}/ask`,
    { invalidateKeys: [qk.user.knowledge.history] },
    'POST',
  );
}

export function useToggleKnowledgeFavorite() {
  return useApiMutation<KnowledgeResource, { id: string; on: boolean }>(
    (vars) => `${PATH}/${vars.id}/favorite`,
    { invalidateKeys: [qk.user.knowledge.root] },
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

function toResource(
  resource: KnowledgeResource,
  run: () => void,
  copyCitation: (resource: KnowledgeResource) => void,
): ResourceItem {
  return {
    id: resource.id,
    name: resource.title,
    description: resource.description,
    meta: `${resource.kind} · ${resource.owner} · ${resource.updated}`,
    filters: { 类型: resource.kind },
    tone: 'bg-[var(--brand-light)] text-[var(--brand)]',
    icon: FileText,
    fields: [
      { label: '类型', value: resource.kind },
      { label: '维护团队', value: resource.owner },
      { label: '更新时间', value: resource.updated },
      { label: '标签', value: resource.tags.join('、') || '—' },
    ],
    note: resource.excerpt,
    extraActions: [{ label: '复制引用', onClick: () => copyCitation(resource) }],
    primary: { label: '带入对话', icon: MessageCircleQuestion, run },
  };
}

export function KnowledgeKind() {
  const navigate = useNavigate();
  const { data: resources = [], isLoading, isFetching, isError, error } = useKnowledgeResources();
  const askMutation = useAskQuestion();
  const favoriteMutation = useToggleKnowledgeFavorite();

  const [query, setQuery] = useState('');
  const [kind, setKind] = useState<KnowledgeFilter | 'favorites'>('all');
  const [tag, setTag] = useState('all');
  const [sort, setSort] = useState<KnowledgeSort>('recent');
  const [favorites, setFavorites] = useState<string[]>([]);
  const [chosenIds, setChosenIds] = useState<string[]>(() => readChosenIds());
  const [browseOpen, setBrowseOpen] = useState(false);
  const [selected, setSelected] = useState<KnowledgeResource | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<{ question: string; resource: KnowledgeResource } | null>(null);
  const [notice, setNotice] = useState('');

  useEffect(() => {
    sessionStorage.setItem(CHOSEN_STORAGE_KEY, JSON.stringify(chosenIds));
  }, [chosenIds]);

  useEffect(() => {
    if (resources.length === 0) return;
    const openIds = new Set(resources.map((item) => item.id));
    setChosenIds((current) => {
      const next = current.filter((id) => openIds.has(id));
      return next.length === current.length ? current : next;
    });
  }, [resources]);

  // 收藏状态由后端按用户存 ✓ —— 刷新后用服务端返回的标记恢复 ✓
  useEffect(() => {
    const serverFavorites = resources.filter((item) => item.favorited).map((item) => item.id);
    if (serverFavorites.length === 0) return;
    setFavorites((current) => {
      const next = Array.from(new Set([...current, ...serverFavorites]));
      return next.length === current.length ? current : next;
    });
  }, [resources]);

  const toggleChosen = (id: string) =>
    setChosenIds((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );

  const ensureChosen = (id: string) =>
    setChosenIds((current) => (current.includes(id) ? current : [...current, id]));

  const toggleFavorite = (resource: KnowledgeResource) => {
    const on = !favorites.includes(resource.id);
    favoriteMutation
      .mutateAsync({ id: resource.id, on })
      .then(() => setFavorites((current) => applyFavorite(current, resource.id, on)))
      .catch((cause) => setNotice(`收藏失败：${String(cause)}`));
  };

  const chosenList = useMemo(
    () => resources.filter((item) => chosenIds.includes(item.id)),
    [resources, chosenIds],
  );

  const allTags = useMemo(
    () =>
      Array.from(new Set(chosenList.flatMap((resource) => resource.tags))).sort((a, b) =>
        a.localeCompare(b, 'zh-CN'),
      ),
    [chosenList],
  );

  const visible = useMemo(() => {
    const filtered = chosenList.filter((resource) => {
      const matchesKind =
        kind === 'all' ||
        (kind === 'favorites' ? favorites.includes(resource.id) : resource.kind === kind);
      const matchesTag = tag === 'all' || resource.tags.includes(tag);
      const text = `${resource.title} ${resource.description} ${resource.owner} ${resource.tags.join(' ')}`.toLowerCase();
      return matchesKind && matchesTag && text.includes(query.trim().toLowerCase());
    });
    return [...filtered].sort((a, b) =>
      sort === 'name' ? a.title.localeCompare(b.title, 'zh-CN') : a.updated.localeCompare(b.updated, 'zh-CN'),
    );
  }, [chosenList, kind, tag, favorites, query, sort]);

  const resetFilters = () => {
    setQuery('');
    setKind('all');
    setTag('all');
    setSort('recent');
  };

  const askPool = chosenList.length > 0 ? chosenList : resources;

  const ask = () => {
    const text = question.trim();
    if (!text || askPool.length === 0) return;
    const resource =
      askPool.find((item) =>
        `${item.title} ${item.tags.join(' ')} ${item.description}`.includes(text),
      ) ?? askPool[0];
    ensureChosen(resource.id);
    askMutation.mutate(
      { question: text },
      {
        onSuccess: (result) => {
          const matched = resources.find((item) => item.id === result.resourceId);
          if (!matched) {
            setAnswer(null);
            setNotice('后端未返回可用的知识引用。');
            return;
          }
          setAnswer({ question: result.question, resource: matched });
          setQuestion('');
        },
        onError: (cause) => setNotice(`提问失败：${String(cause)}`),
      },
    );
  };

  const useKnowledge = (resource: KnowledgeResource) => {
    ensureChosen(resource.id);
    navigate('/copilot', { state: { knowledgeTitle: resource.title } });
  };

  const copyCitation = (resource: KnowledgeResource) => {
    void navigator.clipboard
      .writeText(`${resource.title}\n${resource.excerpt}`)
      .then(() => setNotice(`"${resource.title}"的引用摘要已复制。`))
      .catch((error) => setNotice(`复制失败：${String(error)}`));
  };

  const allResources = useMemo(
    () => resources.map((resource) => toResource(resource, () => useKnowledge(resource), copyCitation)),
    [resources, chosenIds],
  );
  const visibleResources = useMemo(
    () => visible.map((resource) => toResource(resource, () => useKnowledge(resource), copyCitation)),
    [visible, chosenIds],
  );

  return (
    <>
      <PageIntro
        title="知识"
        description="基于企业资料获取可信答案，先选用再提问或带入对话。"
        meta={
          <>
            <span>开放 {resources.length}</span>
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
            <MessageCircleQuestion className="h-3.5 w-3.5" />浏览并选用
          </button>
        }
      />
      {isError && (
        <p role="alert" className="rounded-xl border border-rose-300 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          加载失败：{String(error)}
        </p>
      )}

      <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6">
        <h2 className="text-sm font-semibold">知识问答</h2>
        <p className="mt-1 text-xs text-[var(--text-muted)]">
          输入问题，后端会从已开放的知识里给出引用。
        </p>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            ask();
          }}
          className="mt-4 flex flex-col gap-2 sm:flex-row"
        >
          <label className="sr-only" htmlFor="knowledge-question-input">
            输入知识问题
          </label>
          <input
            id="knowledge-question-input"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="例如：报销标准是什么？"
            className="h-9 min-w-0 flex-1 rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]"
          />
          <button
            type="submit"
            disabled={!question.trim() || askPool.length === 0}
            className="inline-flex h-9 items-center justify-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            检索知识
          </button>
        </form>
        {notice ? (
          <div className="mt-3">
            <NoticeBanner tone="sky" onClose={() => setNotice('')}>
              {notice}
            </NoticeBanner>
          </div>
        ) : null}
        {answer ? (
          <div className="mt-4 rounded-xl border border-dashed border-[var(--border)] bg-[var(--bg-elevated)] p-4">
            <p className="text-[11px] font-semibold text-[var(--brand)]">知识服务返回的参考来源</p>
            <p className="mt-2 text-xs font-medium">{answer.question}</p>
            <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">{answer.resource.excerpt}</p>
            <button
              type="button"
              onClick={() => setSelected(answer.resource)}
              className="mt-3 text-xs font-semibold text-[var(--brand)] hover:underline"
            >
              参考：{answer.resource.title}
            </button>
          </div>
        ) : null}
      </section>

      <ResourceSection
        items={visibleResources}
        query={query}
        onQuery={setQuery}
        searchLabel="搜索知识"
        placeholder="搜索标题、团队或标签"
        filters={[
          {
            label: '类型',
            value: kind,
            onChange: (value) => setKind(value as KnowledgeFilter | 'favorites'),
            options: (['all', '制度', '项目', '指南', 'favorites'] as KnowledgeFilter[]).map((item) => ({
              value: item,
              label: KIND_LABEL[item] ?? item,
            })),
          },
          {
            label: '标签',
            value: tag,
            onChange: (value) => setTag(value),
            options: [
              { value: 'all', label: '全部标签' },
              ...allTags.map((item) => ({ value: item, label: item })),
            ],
          },
          {
            label: '排序',
            value: sort,
            onChange: (value) => setSort(value as KnowledgeSort),
            options: [
              { value: 'recent', label: '最近更新' },
              { value: 'name', label: '按名称' },
            ],
          },
        ]}
        countLabel={`${visibleResources.length} 项`}
        favorited={favorites}
        onToggleFavorite={(id) => {
          const resource = resources.find((item) => item.id === id);
          if (resource) toggleFavorite(resource);
        }}
        onOpenDetails={(item, trigger) => {
          triggerRef.current = trigger;
          setSelected(resources.find((row) => row.id === item.id) ?? null);
        }}
        chosen={chosenIds}
        onToggleChosen={toggleChosen}
        detailsLabel="查看详情"
        loading={isLoading || isFetching}
        empty={{
          title:
            chosenList.length === 0
              ? resources.length === 0
                ? COPY.emptyTitle
                : '还没有选用知识'
              : '没有匹配的知识',
          description:
            chosenList.length === 0
              ? resources.length === 0
                ? COPY.emptyDescription
                : '点击右上角「浏览并选用」，从开放目录中勾选需要的资料。'
              : '尝试其他关键词，或清除筛选后重新查看。',
          action:
            chosenList.length === 0 && resources.length > 0 ? (
              <button
                type="button"
                onClick={() => setBrowseOpen(true)}
                className="text-xs font-semibold text-[var(--brand)] hover:underline"
              >
                去浏览并选用
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

      <ResourceDetailDrawer
        item={selected ? toResource(selected, () => useKnowledge(selected), copyCitation) : null}
        onClose={() => setSelected(null)}
        copy={COPY}
        favorited={selected ? favorites.includes(selected.id) : false}
        onToggleFavorite={() => selected && toggleFavorite(selected)}
        chosen={selected ? chosenIds.includes(selected.id) : false}
        onToggleChosen={() => selected && toggleChosen(selected.id)}
        restoreFocusTo={triggerRef.current}
        onPrimary={() => selected && useKnowledge(selected)}
      />

      <ResourceBrowserDrawer
        open={browseOpen}
        onClose={() => setBrowseOpen(false)}
        items={allResources}
        chosen={chosenIds}
        onToggleChosen={toggleChosen}
        onPrimary={(item) => {
          const resource = resources.find((row) => row.id === item.id);
          if (resource) useKnowledge(resource);
        }}
        loading={isLoading || isFetching}
        copy={COPY}
        searchPlaceholder="搜索标题、描述或标签"
        filters={[
          {
            label: '类型',
            options: (['all', '制度', '项目', '指南'] as KnowledgeKind[]).map((item) => ({
              value: item,
              label: item,
            })),
          },
        ]}
      />
    </>
  );
}
