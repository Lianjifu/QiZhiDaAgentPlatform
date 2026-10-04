import { Activity, CalendarClock, Check, CirclePlay, Heart, Workflow } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { CenterModal } from '@/components/feedback/CenterModal';
import { NoticeBanner } from '@/components/feedback/NoticeBanner';
import { SideDrawer } from '@/components/feedback/SideDrawer';
import { CardActionButton, CardActions, CatalogToolbar, EmptyFilterState, PageIntro, WorkspacePage } from '../components';
import { BrowseWorkflowsDrawer } from './components/BrowseWorkflowsDrawer';
import { useFlows, useFlowRuns, useRecordFlowRun } from './useAutomations';
import type { Flow, FlowRun, FlowAvailability } from './schema';

const CHOSEN_STORAGE_KEY = 'qzdap.user.automations.chosen';

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

export default function AutomationsPage() {
  const { data: flows = [], isLoading, isFetching, refetch } = useFlows();
  const { data: remoteRuns = [] } = useFlowRuns();
  const recordRun = useRecordFlowRun();

  const [runs, setRuns] = useState<FlowRun[]>([]);
  const [favorites, setFavorites] = useState<string[]>([]);
  const [chosenIds, setChosenIds] = useState<string[]>(() => readChosenIds());
  const [browseOpen, setBrowseOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [availabilityFilter, setAvailabilityFilter] = useState<'all' | FlowAvailability>('all');
  const [scene, setScene] = useState('全部场景');
  const [selected, setSelected] = useState<Flow | null>(null);
  const [runTarget, setRunTarget] = useState<Flow | null>(null);
  const [runNote, setRunNote] = useState('');
  const [notice, setNotice] = useState('');
  const browseTriggerRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    setRuns(remoteRuns);
  }, [remoteRuns]);

  useEffect(() => {
    sessionStorage.setItem(CHOSEN_STORAGE_KEY, JSON.stringify(chosenIds));
  }, [chosenIds]);

  useEffect(() => {
    if (flows.length === 0) return;
    const openIds = new Set(flows.map((flow) => flow.id));
    setChosenIds((current) => {
      const next = current.filter((id) => openIds.has(id));
      return next.length === current.length ? current : next;
    });
  }, [flows]);

  const chosenList = useMemo(
    () => flows.filter((flow) => chosenIds.includes(flow.id)),
    [flows, chosenIds],
  );

  const sceneOptions = useMemo(() => {
    const present = Array.from(new Set(chosenList.map((flow) => flow.scene)));
    return ['全部场景', ...present];
  }, [chosenList]);

  const visible = useMemo(() => chosenList.filter((flow) =>
    (availabilityFilter === 'all' || flow.availability === availabilityFilter) &&
    (scene === '全部场景' || flow.scene === scene) &&
    `${flow.name} ${flow.description} ${flow.owner}`.toLowerCase().includes(search.trim().toLowerCase()),
  ), [chosenList, availabilityFilter, scene, search]);

  const availableCount = flows.filter((flow) => flow.availability === 'available').length;

  const toggleChosen = (id: string) => {
    setChosenIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  };

  const ensureChosen = (id: string) => {
    setChosenIds((current) => current.includes(id) ? current : [...current, id]);
  };

  const browseWorkflows = async () => {
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
    const next: FlowRun = {
      id: `local-${Date.now()}`,
      name: runTarget.name,
      time: '刚刚 · 本地演示',
      result: runNote.trim() ? '已记录使用说明' : '演示完成',
    };
    setRuns((current) => [next, ...current]);
    setNotice(`"${runTarget.name}"已加入本地使用记录，未触发真实工作流。`);
    setRunNote('');
    setRunTarget(null);
    setBrowseOpen(false);
    recordRun.mutate({ flowId: runTarget.id, note: runNote });
  };

  const toggleFavorite = (flow: Flow) =>
    setFavorites((current) => current.includes(flow.id) ? current.filter((id) => id !== flow.id) : [...current, flow.id]);

  const resetFilters = () => {
    setSearch('');
    setAvailabilityFilter('all');
    setScene('全部场景');
  };

  return (
    <WorkspacePage>
      <PageIntro
        title="工作流"
        description="从工作流管理已发布的流程中选用，加入后可在此使用。"
        meta={
          <>
            <span>可浏览 {availableCount}</span>
            <span>工作流 {chosenList.length}</span>
            <span>收藏 {favorites.length}</span>
            <span>最近使用 {runs.length}</span>
            {(isLoading || isFetching) && <span>同步中…</span>}
          </>
        }
        actions={
          <button
            ref={browseTriggerRef}
            type="button"
            onClick={() => { void browseWorkflows(); }}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-[var(--brand)] px-3 text-xs font-semibold text-white hover:bg-[var(--brand-hover)]"
          >
            <CirclePlay className="h-3.5 w-3.5" />浏览工作流
          </button>
        }
      />
      {notice && <NoticeBanner tone="amber" onClose={() => setNotice('')}>{notice}</NoticeBanner>}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_280px]">
        <section id="automation-list" aria-labelledby="automation-list-title" className="min-w-0 overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
          <h3 id="automation-list-title" className="sr-only">工作流列表</h3>
          <CatalogToolbar
            search={search}
            onSearch={setSearch}
            searchLabel="搜索工作流"
            placeholder="搜索工作流、场景或团队"
            filters={[
              {
                label: '可用性',
                value: availabilityFilter,
                onChange: (value) => setAvailabilityFilter(value as 'all' | FlowAvailability),
                options: [
                  { value: 'all', label: '全部' },
                  { value: 'available', label: '可使用' },
                  { value: 'unavailable', label: '暂不可用' },
                ],
              },
              {
                label: '场景',
                value: scene,
                onChange: (value) => setScene(value),
                options: sceneOptions.map((item) => ({ value: item, label: item })),
              },
            ]}
            countLabel={`${visible.length} 项`}
          />
          {visible.length ? (
            <div className="grid gap-4 p-5 md:grid-cols-2 xl:grid-cols-3">
              {visible.map((flow) => (
                <article key={flow.id} className="group flex min-h-[250px] flex-col rounded-2xl border border-[var(--border)] p-5 transition hover:border-[var(--brand)] hover:shadow-[var(--shadow-sm)]">
                  <div className="flex items-start justify-between gap-3">
                    <span className="grid h-10 w-10 place-items-center rounded-xl bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300">
                      <Workflow className="h-5 w-5" />
                    </span>
                    <button
                      type="button"
                      aria-label={`${favorites.includes(flow.id) ? '取消收藏' : '收藏'}${flow.name}`}
                      aria-pressed={favorites.includes(flow.id)}
                      onClick={() => toggleFavorite(flow)}
                      className={`rounded-lg p-2 ${favorites.includes(flow.id) ? 'text-rose-500' : 'text-[var(--text-muted)] hover:text-rose-500'}`}
                    >
                      <Heart className="h-4 w-4" fill={favorites.includes(flow.id) ? 'currentColor' : 'none'} />
                    </button>
                  </div>
                  <div className="mt-4 flex flex-wrap items-center gap-2">
                    <span className="text-[10px] font-semibold text-[var(--text-muted)]">{flow.scene}</span>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${flow.availability === 'available' ? 'bg-[var(--success-bg)] text-[var(--success)]' : 'bg-[var(--bg-hover)] text-[var(--text-muted)]'}`}>
                      {flow.availability === 'available' ? '可使用' : '暂不可用'}
                    </span>
                  </div>
                  <button type="button" onClick={() => setSelected(flow)} className="mt-2 text-left text-base font-semibold hover:text-[var(--brand)]">{flow.name}</button>
                  <p className="mt-2 line-clamp-2 text-xs leading-6 text-[var(--text-muted)]">{flow.description}</p>
                  <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-[var(--text-muted)]">
                    <span className="inline-flex items-center gap-1"><CalendarClock className="h-3.5 w-3.5" />{flow.cadence}</span>
                    <span>{flow.lastRun}</span>
                    <span>{flow.owner}</span>
                  </div>
                  <CardActions>
                    <CardActionButton aria-label={`移出${flow.name}`} onClick={() => toggleChosen(flow.id)}>移出</CardActionButton>
                    <CardActionButton onClick={() => setSelected(flow)}>查看步骤</CardActionButton>
                    <CardActionButton
                      tone="brand"
                      disabled={flow.availability !== 'available'}
                      onClick={() => openUse(flow)}
                    >
                      <CirclePlay className="h-3.5 w-3.5" />使用工作流
                    </CardActionButton>
                  </CardActions>
                </article>
              ))}
            </div>
          ) : (
            <EmptyFilterState
              title={chosenList.length === 0 ? (flows.length === 0 ? '管理员尚未发布工作流' : '还没有工作流') : '没有匹配的工作流'}
              description={
                chosenList.length === 0
                  ? (flows.length === 0
                    ? '请在工作流管理中发布流程后再来选用。'
                    : '点击「浏览工作流」，从已发布目录中加入工作流。')
                  : '尝试其他关键词、场景或可用性。'
              }
              action={
                chosenList.length === 0 && flows.length > 0 ? (
                  <button type="button" onClick={() => { void browseWorkflows(); }} className="text-xs font-semibold text-[var(--brand)] hover:underline">
                    去浏览工作流
                  </button>
                ) : chosenList.length > 0 ? (
                  <button type="button" onClick={resetFilters} className="text-xs font-semibold text-[var(--brand)] hover:underline">
                    清除筛选
                  </button>
                ) : null
              }
            />
          )}
        </section>

        <aside>
          <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
            <h3 className="flex items-center gap-2 text-sm font-semibold"><Activity className="h-4 w-4 text-[var(--brand)]" />最近使用</h3>
            <p className="mt-2 text-xs text-[var(--text-muted)]">本地演示记录，不代表真实执行。</p>
            {runs.length === 0 ? (
              <p className="mt-5 text-xs leading-6 text-[var(--text-muted)]">加入并使用后，会显示在这里。</p>
            ) : (
              <ol className="mt-5 space-y-0">
                {runs.slice(0, 5).map((run) => (
                  <li key={run.id} className="relative border-l border-[var(--border)] pb-5 pl-5 last:pb-0">
                    <span className="absolute -left-[5px] top-1.5 h-2.5 w-2.5 rounded-full bg-[var(--brand)] ring-4 ring-[var(--surface-1)]" />
                    <p className="text-xs font-semibold">{run.name}</p>
                    <p className="mt-1 text-[11px] text-[var(--text-muted)]">{run.time} · {run.result}</p>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </aside>
      </div>

      <BrowseWorkflowsDrawer
        open={browseOpen}
        flows={flows}
        chosenIds={chosenIds}
        loading={isLoading || isFetching}
        onClose={closeBrowse}
        onToggleChosen={toggleChosen}
        onUse={openUse}
      />

      <SideDrawer
        open={selected !== null}
        onClose={() => setSelected(null)}
        ariaLabel={selected ? `${selected.name}工作流详情` : '工作流详情'}
        eyebrow={<p className="text-[11px] font-semibold text-[var(--brand)]">工作流详情 · {selected?.scene ?? ''}</p>}
        closeLabel="关闭工作流详情"
      >
        {selected && (
          <>
            <span className="mt-10 grid h-14 w-14 place-items-center rounded-2xl bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300">
              <Workflow className="h-7 w-7" />
            </span>
            <h3 className="mt-5 text-2xl font-semibold">{selected.name}</h3>
            <p className="mt-3 text-sm leading-7 text-[var(--text-muted)]">{selected.description}</p>
            <div className="mt-7 grid grid-cols-2 gap-3 text-xs">
              <div className="rounded-xl bg-[var(--bg-elevated)] p-4">
                <p className="text-[var(--text-muted)]">使用方式</p>
                <p className="mt-2 font-semibold">{selected.cadence}</p>
              </div>
              <div className="rounded-xl bg-[var(--bg-elevated)] p-4">
                <p className="text-[var(--text-muted)]">当前状态</p>
                <p className="mt-2 font-semibold">{selected.availability === 'available' ? '可使用' : '暂不可用'}</p>
              </div>
            </div>
            <h4 className="mt-9 text-sm font-semibold">执行步骤</h4>
            <ol className="mt-4 space-y-3">
              {selected.steps.map((step, idx) => (
                <li key={`${step}-${idx}`} className="flex items-center gap-4 rounded-xl border border-[var(--border)] p-4">
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[var(--brand-light)] text-xs font-bold text-[var(--brand)]">{idx + 1}</span>
                  <span className="text-sm font-medium">{step}</span>
                  {idx === selected.steps.length - 1 && <Check className="ml-auto h-4 w-4 text-[var(--success)]" />}
                </li>
              ))}
            </ol>
            <div className="mt-7 flex flex-col gap-2 sm:flex-row">
              <button
                type="button"
                onClick={() => toggleChosen(selected.id)}
                className="inline-flex items-center justify-center rounded-xl border border-[var(--border)] px-4 py-3 text-sm font-semibold"
              >
                {chosenIds.includes(selected.id) ? '移出工作流' : '加入工作流'}
              </button>
              <button
                type="button"
                disabled={selected.availability !== 'available'}
                onClick={() => { openUse(selected); setSelected(null); }}
                className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl bg-[var(--brand)] px-4 py-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
              >
                <CirclePlay className="h-4 w-4" />使用这个工作流
              </button>
            </div>
            <p className="mt-4 text-xs leading-6 text-[var(--text-muted)]">工作流由管理员维护；使用操作只会创建当前页面的演示记录。</p>
          </>
        )}
      </SideDrawer>
      <CenterModal
        open={runTarget !== null}
        onClose={() => setRunTarget(null)}
        ariaLabel={runTarget ? `使用${runTarget.name}` : '使用工作流'}
        title={runTarget ? `使用工作流：${runTarget.name}` : '使用工作流'}
        description="确认后会创建一条本地演示使用记录，不会触发真实工作流。"
        closeLabel="关闭使用工作流窗口"
        onSubmit={(event) => { event.preventDefault(); runFlow(); }}
        footer={
          <>
            <button type="button" onClick={() => setRunTarget(null)} className="rounded-xl border border-[var(--border)] px-4 py-2.5 text-sm font-medium">取消</button>
            <button type="submit" className="inline-flex items-center gap-2 rounded-xl bg-[var(--brand)] px-4 py-2.5 text-sm font-semibold text-white">
              <CirclePlay className="h-4 w-4" />确认使用
            </button>
          </>
        }
      >
        <label className="mt-6 block text-xs font-semibold">给这次使用添加说明（可选）
          <textarea
            value={runNote}
            onChange={(event) => setRunNote(event.target.value)}
            placeholder="例如：整理本周华东客户进展"
            className="mt-2 min-h-24 w-full resize-y rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] p-3 text-sm font-normal outline-none focus:border-[var(--brand)]"
          />
        </label>
      </CenterModal>
    </WorkspacePage>
  );
}
