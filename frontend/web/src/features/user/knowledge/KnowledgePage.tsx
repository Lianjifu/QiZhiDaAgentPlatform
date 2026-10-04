import { BookOpen, Check, FilePlus2, FileText, Heart, MessageCircleQuestion, Share2, Sparkles } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useEffect, useMemo, useRef, useState } from 'react';
import { NoticeBanner } from '@/components/feedback/NoticeBanner';
import { SideDrawer } from '@/components/feedback/SideDrawer';
import { CardActionButton, CardActions, CatalogToolbar, EmptyFilterState, PageIntro, WorkspacePage } from '../components';
import { BrowseKnowledgeDrawer } from './components/BrowseKnowledgeDrawer';
import { useKnowledgeResources } from './useKnowledge';
import type { KnowledgeResource, KnowledgeFilter, KnowledgeSort } from './schema';

const CHOSEN_STORAGE_KEY = 'qzdap.user.knowledge.chosen';

const kinds: Array<KnowledgeFilter | 'favorites'> = ['all', '制度', '项目', '指南', 'favorites'];
const KIND_LABEL: Record<KnowledgeFilter | 'favorites', string> = {
  all: '全部类型', 制度: '制度', 项目: '项目', 指南: '指南', favorites: '已收藏',
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

export default function KnowledgePage() {
  const navigate = useNavigate();
  const { data: remoteList = [], isLoading, isFetching, refetch } = useKnowledgeResources();
  const resources = remoteList;

  const [query, setQuery] = useState('');
  const [kind, setKind] = useState<KnowledgeFilter | 'favorites'>('all');
  const [tag, setTag] = useState('all');
  const [sort, setSort] = useState<KnowledgeSort>('recent');
  const [favorites, setFavorites] = useState<string[]>([]);
  const [chosenIds, setChosenIds] = useState<string[]>(() => readChosenIds());
  const [browseOpen, setBrowseOpen] = useState(false);
  const [selected, setSelected] = useState<KnowledgeResource | null>(null);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<{ question: string; resource: KnowledgeResource } | null>(null);
  const [notice, setNotice] = useState('');
  const browseTriggerRef = useRef<HTMLButtonElement | null>(null);

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

  const chosenList = useMemo(
    () => resources.filter((item) => chosenIds.includes(item.id)),
    [resources, chosenIds],
  );

  const allTags = useMemo(
    () => Array.from(new Set(chosenList.flatMap((resource) => resource.tags))).sort((a, b) => a.localeCompare(b, 'zh-CN')),
    [chosenList],
  );

  const visible = useMemo(() => {
    const filtered = chosenList.filter((resource) => {
      const matchesKind = kind === 'all' || (kind === 'favorites' ? favorites.includes(resource.id) : resource.kind === kind);
      const matchesTag = tag === 'all' || resource.tags.includes(tag);
      const text = `${resource.title} ${resource.description} ${resource.owner} ${resource.tags.join(' ')}`.toLowerCase();
      return matchesKind && matchesTag && text.includes(query.trim().toLowerCase());
    });
    return [...filtered].sort((a, b) =>
      sort === 'name' ? a.title.localeCompare(b.title, 'zh-CN') : a.updated.localeCompare(b.updated, 'zh-CN'),
    );
  }, [chosenList, kind, tag, favorites, query, sort]);

  const resetFilters = () => { setQuery(''); setKind('all'); setTag('all'); setSort('recent'); };

  const toggleChosen = (id: string) => {
    setChosenIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  };

  const ensureChosen = (id: string) => {
    setChosenIds((current) => current.includes(id) ? current : [...current, id]);
  };

  const askPool = chosenList.length > 0 ? chosenList : resources;

  const ask = () => {
    const text = question.trim();
    if (!text || askPool.length === 0) return;
    const resource = askPool.find((item) => `${item.title} ${item.tags.join(' ')} ${item.description}`.includes(text)) ?? askPool[0];
    ensureChosen(resource.id);
    setAnswer({ question: text, resource });
    setQuestion('');
  };

  const browseKnowledge = async () => {
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

  const toggleFavorite = (resource: KnowledgeResource) =>
    setFavorites((current) => current.includes(resource.id) ? current.filter((id) => id !== resource.id) : [...current, resource.id]);

  const copyCitation = (resource: KnowledgeResource) => {
    setNotice(`"${resource.title}"的引用摘要已复制（本地演示）。`);
  };

  const useKnowledge = (resource: KnowledgeResource) => {
    ensureChosen(resource.id);
    navigate('/copilot', { state: { knowledgeTitle: resource.title } });
  };

  return (
    <WorkspacePage>
      <PageIntro
        title="知识"
        description="从知识管理已索引并对工作区开放的文档中选用，加入后可提问或带入对话。"
        meta={
          <>
            <span>可浏览 {resources.length}</span>
            <span>知识 {chosenList.length}</span>
            <span>收藏 {favorites.length}</span>
            {(isLoading || isFetching) && <span>同步中…</span>}
          </>
        }
        actions={
          <button
            ref={browseTriggerRef}
            type="button"
            onClick={() => { void browseKnowledge(); }}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]"
          >
            <BookOpen className="h-3.5 w-3.5" />浏览资料
          </button>
        }
      />
      {notice && <NoticeBanner tone="emerald" onClose={() => setNotice('')}>{notice}</NoticeBanner>}

      <section id="knowledge-ask" className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 sm:p-6">
        <div className="flex items-start gap-3">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[var(--brand-light)] text-[var(--brand)]"><Sparkles className="h-4 w-4" /></span>
          <div>
            <h3 className="text-sm font-semibold">基于资料提问</h3>
            <p className="mt-1 text-xs text-[var(--text-muted)]">
              {chosenList.length === 0 ? '先浏览并加入资料，再基于知识查看示例回答。' : '在已加入的资料中查看示例回答与参考来源。'}
            </p>
          </div>
        </div>
        <form onSubmit={(event) => { event.preventDefault(); ask(); }} className="mt-4 flex flex-col gap-2 sm:flex-row">
          <label className="sr-only" htmlFor="knowledge-question-input">输入知识问题</label>
          <input
            id="knowledge-question-input"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="例如：入职第一周要完成什么？"
            className="h-9 min-w-0 flex-1 rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] px-3 text-sm outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--brand)]"
          />
          <button type="submit" disabled={!question.trim() || askPool.length === 0} className="inline-flex h-9 items-center justify-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40">
            查看示例
          </button>
        </form>
        {answer && (
          <div className="mt-4 rounded-xl border border-dashed border-[var(--border)] bg-[var(--bg-elevated)] p-4">
            <p className="text-[11px] font-semibold text-[var(--brand)]">示例回答 · 未连接知识服务</p>
            <p className="mt-2 text-xs font-medium">{answer.question}</p>
            <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">{answer.resource.excerpt}</p>
            <button type="button" onClick={() => setSelected(answer.resource)} className="mt-3 text-xs font-semibold text-[var(--brand)] hover:underline">
              参考：{answer.resource.title}
            </button>
          </div>
        )}
      </section>

      <section aria-labelledby="knowledge-list-title" className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
        <h3 id="knowledge-list-title" className="sr-only">知识列表</h3>
        <CatalogToolbar
          search={query}
          onSearch={setQuery}
          searchLabel="搜索资料"
          placeholder="搜索标题、团队或标签"
          filters={[
            {
              label: '资料类型',
              value: kind,
              onChange: (value) => setKind(value as KnowledgeFilter | 'favorites'),
              options: kinds.map((item) => ({ value: item, label: KIND_LABEL[item] })),
            },
            {
              label: '标签',
              value: tag,
              onChange: setTag,
              options: [{ value: 'all', label: '全部标签' }, ...allTags.map((item) => ({ value: item, label: item }))],
            },
            {
              label: '排序',
              value: sort,
              onChange: (value) => setSort(value as KnowledgeSort),
              options: [
                { value: 'recent', label: '最近更新' },
                { value: 'name', label: '名称排序' },
              ],
            },
          ]}
          countLabel={`${visible.length} 项`}
        />
        {visible.length ? (
          <div className="grid gap-4 p-5 md:grid-cols-2 xl:grid-cols-3">
            {visible.map((resource) => (
              <article key={resource.id} className="group flex min-h-[220px] flex-col rounded-2xl border border-[var(--border)] p-5 transition hover:border-[var(--brand)] hover:shadow-[var(--shadow-sm)]">
                <div className="flex items-start justify-between">
                  <span className="grid h-10 w-10 place-items-center rounded-xl bg-[var(--brand-light)] text-[var(--brand)]">
                    {resource.kind === '指南' ? <BookOpen className="h-5 w-5" /> : resource.kind === '项目' ? <FilePlus2 className="h-5 w-5" /> : <FileText className="h-5 w-5" />}
                  </span>
                  <button type="button" aria-label={`${favorites.includes(resource.id) ? '取消收藏' : '收藏'}${resource.title}`} aria-pressed={favorites.includes(resource.id)} onClick={() => toggleFavorite(resource)} className={`rounded-lg p-2 transition ${favorites.includes(resource.id) ? 'text-rose-500' : 'text-[var(--text-muted)] hover:text-rose-500'}`}>
                    <Heart className="h-4 w-4" fill={favorites.includes(resource.id) ? 'currentColor' : 'none'} />
                  </button>
                </div>
                <button type="button" onClick={() => setSelected(resource)} className="mt-4 text-left">
                  <span className="text-[10px] font-semibold text-[var(--text-muted)]">{resource.kind} · {resource.updated}</span>
                  <h4 className="mt-2 text-base font-semibold leading-6 group-hover:text-[var(--brand)]">{resource.title}</h4>
                  <p className="mt-2 line-clamp-2 text-xs leading-6 text-[var(--text-muted)]">{resource.description}</p>
                </button>
                <p className="mt-3 text-[11px] text-[var(--text-muted)]">{resource.owner}</p>
                <CardActions>
                  <CardActionButton aria-label={`移出${resource.title}`} onClick={() => toggleChosen(resource.id)}>移出</CardActionButton>
                  <CardActionButton onClick={() => setSelected(resource)}>查看详情</CardActionButton>
                  <CardActionButton tone="brand" onClick={() => useKnowledge(resource)}>
                    <MessageCircleQuestion className="h-3.5 w-3.5" />带入对话
                  </CardActionButton>
                </CardActions>
              </article>
            ))}
          </div>
        ) : (
          <EmptyFilterState
            title={chosenList.length === 0 ? (resources.length === 0 ? '管理员尚未开放资料' : '还没有知识') : '没有找到匹配的资料'}
            description={
              chosenList.length === 0
                ? (resources.length === 0
                  ? '请在知识管理中索引公开/部门知识库后再来选用。'
                  : '点击「浏览资料」，从已开放文档中加入知识。')
                : '试试其他关键词，或清除筛选条件。'
            }
            action={
              chosenList.length === 0 && resources.length > 0 ? (
                <button type="button" onClick={() => { void browseKnowledge(); }} className="text-xs font-semibold text-[var(--brand)] hover:underline">
                  去浏览资料
                </button>
              ) : chosenList.length > 0 ? (
                <button type="button" onClick={resetFilters} className="text-xs font-semibold text-[var(--brand)] hover:underline">清除全部筛选</button>
              ) : null
            }
          />
        )}
      </section>

      <BrowseKnowledgeDrawer
        open={browseOpen}
        resources={resources}
        chosenIds={chosenIds}
        loading={isLoading || isFetching}
        onClose={closeBrowse}
        onToggleChosen={toggleChosen}
        onUse={useKnowledge}
      />

      <SideDrawer
        open={selected !== null}
        onClose={() => setSelected(null)}
        ariaLabel={selected ? `${selected.title}详情` : '资料详情'}
        eyebrow={<span className="text-[11px] font-semibold text-[var(--brand)]">资料详情 · {selected?.kind ?? ''}</span>}
        closeLabel="关闭资料详情"
        panelClassName="flex flex-col"
      >
        {selected && (
          <>
            <div className="mt-10 grid h-14 w-14 place-items-center rounded-2xl bg-[var(--brand-light)] text-[var(--brand)]">
              <BookOpen className="h-7 w-7" />
            </div>
            <h3 className="mt-5 text-2xl font-semibold leading-9">{selected.title}</h3>
            <p className="mt-3 text-sm leading-7 text-[var(--text-muted)]">{selected.description}</p>
            <div className="mt-7 flex flex-wrap gap-2">
              {selected.tags.map((item) => <span key={item} className="rounded-full bg-[var(--bg-elevated)] px-3 py-1.5 text-xs text-[var(--text-secondary)]">{item}</span>)}
            </div>
            <div className="mt-8 divide-y divide-[var(--border)] rounded-2xl border border-[var(--border)] px-5">
              <div className="flex justify-between gap-4 py-4 text-xs">
                <span className="text-[var(--text-muted)]">维护团队</span>
                <span className="font-semibold">{selected.owner}</span>
              </div>
              <div className="flex justify-between gap-4 py-4 text-xs">
                <span className="text-[var(--text-muted)]">最近更新</span>
                <span className="font-semibold">{selected.updated}</span>
              </div>
              <div className="flex justify-between gap-4 py-4 text-xs">
                <span className="text-[var(--text-muted)]">引用状态</span>
                <span className="inline-flex items-center gap-1 font-semibold text-[var(--success)]">
                  <Check className="h-3.5 w-3.5" />示例来源信息
                </span>
              </div>
            </div>
            <div className="mt-8 rounded-2xl bg-[var(--bg-elevated)] p-5">
              <p className="text-xs font-semibold">内容摘要 · 演示</p>
              <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">{selected.excerpt}</p>
            </div>
            <CardActions>
              <CardActionButton onClick={() => toggleChosen(selected.id)}>
                {chosenIds.includes(selected.id) ? '移出知识' : '加入知识'}
              </CardActionButton>
              <CardActionButton onClick={() => toggleFavorite(selected)}>
                <Heart className="h-3.5 w-3.5" fill={favorites.includes(selected.id) ? 'currentColor' : 'none'} />
                {favorites.includes(selected.id) ? '取消收藏' : '收藏'}
              </CardActionButton>
              <CardActionButton tone="brand" onClick={() => useKnowledge(selected)}>
                <MessageCircleQuestion className="h-3.5 w-3.5" />带入对话
              </CardActionButton>
              <CardActionButton onClick={() => copyCitation(selected)}>
                <Share2 className="h-3.5 w-3.5" />复制引用
              </CardActionButton>
            </CardActions>
            <p className="mt-6 text-xs leading-6 text-[var(--text-muted)]">资料由管理员维护；你可以收藏、阅读并将它用于当前工作。</p>
          </>
        )}
      </SideDrawer>
    </WorkspacePage>
  );
}
