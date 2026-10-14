import { Plus, Search } from 'lucide-react';
import { FlaskConical, GitBranch, ShieldCheck, Sparkles } from 'lucide-react';
import type { CaseTemplate, EvalResult, EvalSuite, EvalSuiteType, EvalStatus } from '../../schema';
import { SuiteCard } from '../SuiteCard';
import { BatchToolbar } from '../BatchToolbar';
import { STATUS_BADGE, STATUS_FILTER, TYPE_FILTER, TYPE_META, caseStatusClass, caseStatusLabel, uid } from '../constants';

const tplIconMap: Record<string, typeof Sparkles> = {
  Sparkles,
  FlaskConical,
  ShieldCheck,
  GitBranch,
};

interface OverviewTabProps {
  visibleSuites: EvalSuite[];
  results: EvalResult[];
  suitesCount: number;
  selectedIds: string[];
  setSelectedIds: (ids: string[]) => void;
  openMenuId: string | null;
  setOpenMenuId: (id: string | null) => void;
  search: string;
  setSearch: (s: string) => void;
  typeFilter: 'all' | EvalSuiteType;
  setTypeFilter: (t: 'all' | EvalSuiteType) => void;
  statusFilter: 'all' | EvalStatus;
  setStatusFilter: (s: 'all' | EvalStatus) => void;
  onSelect: (s: EvalSuite) => void;
  onToggleStar: (id: string) => void;
  onToggleSelect: (id: string) => void;
  onRun: (s: EvalSuite) => void;
  onDuplicate: (s: EvalSuite) => void;
  onRequestDelete: (s: EvalSuite) => void;
  onBatchRun: () => void;
  onBatchDelete: () => void;
}

export function OverviewTab(props: OverviewTabProps) {
  const {
    visibleSuites, results, suitesCount, selectedIds, setSelectedIds,
    openMenuId, setOpenMenuId, search, setSearch,
    typeFilter, setTypeFilter, statusFilter, setStatusFilter,
    onSelect, onToggleStar, onToggleSelect, onRun, onDuplicate, onRequestDelete,
    onBatchRun, onBatchDelete,
  } = props;
  return (
    <>
      <div className="space-y-4">
        {selectedIds.length > 0 && (
          <BatchToolbar
            count={selectedIds.length}
            onClear={() => setSelectedIds([])}
            onBatchRun={onBatchRun}
            onBatchDelete={onBatchDelete}
          />
        )}
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-teal-700 dark:text-teal-300">评测总览</p>
              <h3 className="mt-2 text-lg font-semibold">套件目录</h3>
              <p className="mt-1 text-xs text-[var(--text-muted)]">{visibleSuites.length} 个套件结果 · {results.length} 条最近运行记录</p>
            </div>
            <div className="relative w-full xl:max-w-xs">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]" />
              <label className="sr-only" htmlFor="eval-search">搜索套件</label>
              <input id="eval-search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="搜索套件 / 标签" className="h-10 w-full rounded-xl border border-[var(--border)] bg-[var(--surface-1)] pl-10 pr-3 text-sm outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--brand)]" />
            </div>
          </div>
          <div className="mt-5 flex flex-wrap items-center gap-2">
            <label className="sr-only" htmlFor="eval-type">按类型筛选</label>
            <select id="eval-type" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value as 'all' | EvalSuiteType)} className="h-9 rounded-xl border border-[var(--border)] bg-[var(--surface-1)] px-3 text-xs font-medium outline-none">
              {TYPE_FILTER.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
            </select>
            <label className="sr-only" htmlFor="eval-status">按状态筛选</label>
            <select id="eval-status" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as 'all' | EvalStatus)} className="h-9 rounded-xl border border-[var(--border)] bg-[var(--surface-1)] px-3 text-xs font-medium outline-none">
              {STATUS_FILTER.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
            </select>
          </div>
          <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {visibleSuites.map((suite) => (
              <SuiteCard
                key={suite.id}
                suite={suite}
                onSelect={onSelect}
                onToggleStar={onToggleStar}
                selected={selectedIds.includes(suite.id)}
                onToggleSelect={onToggleSelect}
                onRun={onRun}
                onDuplicate={onDuplicate}
                onRequestDelete={onRequestDelete}
              />
            ))}
          </div>
          {visibleSuites.length === 0 && (
            <div className="mt-5 rounded-2xl border border-dashed border-[var(--border-strong)] p-12 text-center">
              <Search className="mx-auto h-6 w-6 text-[var(--text-muted)]" />
              <p className="mt-3 text-sm font-semibold">没有匹配的套件</p>
              <p className="mt-1 text-xs text-[var(--text-muted)]">尝试其他关键词或清除筛选。</p>
            </div>
          )}
        </div>
      </div>

      <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">最近运行</p>
            <h3 className="mt-2 text-lg font-semibold">最近评测结果</h3>
          </div>
        </div>
        <div className="mt-4 overflow-x-auto rounded-xl border border-[var(--border)]">
          <table className="w-full text-left text-xs">
            <thead className="bg-[var(--bg-elevated)] text-[var(--text-muted)]">
              <tr>
                <th className="px-3 py-2 font-semibold">套件</th>
                <th className="px-3 py-2 font-semibold">对象</th>
                <th className="px-3 py-2 font-semibold">运行时间</th>
                <th className="px-3 py-2 font-semibold">状态</th>
                <th className="px-3 py-2 font-semibold">通过率</th>
                <th className="px-3 py-2 font-semibold">评分</th>
                <th className="px-3 py-2 font-semibold">耗时</th>
                <th className="px-3 py-2 font-semibold">成本</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r) => {
                const badge = STATUS_BADGE[r.status];
                return (
                  <tr key={r.id} className="border-t border-[var(--border)]">
                    <td className="px-3 py-2 font-semibold">{r.suite}</td>
                    <td className="px-3 py-2 text-[var(--text-muted)]">{r.target}</td>
                    <td className="px-3 py-2 text-[var(--text-muted)]">{r.runAt}</td>
                    <td className="px-3 py-2"><span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${badge.className}`}><span className={`h-1.5 w-1.5 rounded-full ${badge.dot}`} aria-hidden="true" />{badge.label}</span></td>
                    <td className="px-3 py-2 tabular-nums">{r.passRate.toFixed(1)}%</td>
                    <td className="px-3 py-2 tabular-nums">{r.avgScore.toFixed(1)}</td>
                    <td className="px-3 py-2 text-[var(--text-muted)]">{r.duration}</td>
                    <td className="px-3 py-2 text-[var(--text-muted)]">{r.cost}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <span className="sr-only">{suitesCount}</span>
      </section>
    </>
  );
}

interface SuiteListTabProps {
  visibleSuites: EvalSuite[];
  selectedIds: string[];
  openMenuId: string | null;
  setOpenMenuId: (id: string | null) => void;
  onSelect: (s: EvalSuite) => void;
  onToggleStar: (id: string) => void;
  onToggleSelect: (id: string) => void;
  onRun: (s: EvalSuite) => void;
  onDuplicate: (s: EvalSuite) => void;
  onRequestDelete: (s: EvalSuite) => void;
}

export function SuiteListTab({
  visibleSuites, selectedIds, openMenuId, setOpenMenuId,
  onSelect, onToggleStar, onToggleSelect, onRun, onDuplicate, onRequestDelete,
}: SuiteListTabProps) {
  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-teal-700 dark:text-teal-300">评测套件</p>
      <h3 className="mt-2 text-lg font-semibold">所有套件</h3>
      <p className="mt-1 text-xs text-[var(--text-muted)]">统一管理与运行所有评测套件,展开查看详情。</p>
      <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {visibleSuites.map((suite) => (
          <SuiteCard
            key={suite.id}
            suite={suite}
            onSelect={onSelect}
            onToggleStar={onToggleStar}
            selected={selectedIds.includes(suite.id)}
            onToggleSelect={onToggleSelect}
            onRun={onRun}
            onDuplicate={onDuplicate}
            onRequestDelete={onRequestDelete}
          />
        ))}
      </div>
    </section>
  );
}

export function ResultTab({ results }: { results: EvalResult[] }) {
  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-teal-700 dark:text-teal-300">评测结果</p>
      <h3 className="mt-2 text-lg font-semibold">运行历史</h3>
      <p className="mt-1 text-xs text-[var(--text-muted)]">点击行查看套件详情;支持按套件名搜索。</p>
      <div className="mt-5 overflow-x-auto rounded-xl border border-[var(--border)]">
        <table className="w-full text-left text-xs">
          <thead className="bg-[var(--bg-elevated)] text-[var(--text-muted)]">
            <tr>
              <th className="px-3 py-2 font-semibold">套件</th>
              <th className="px-3 py-2 font-semibold">对象</th>
              <th className="px-3 py-2 font-semibold">运行时间</th>
              <th className="px-3 py-2 font-semibold">状态</th>
              <th className="px-3 py-2 font-semibold">通过率</th>
              <th className="px-3 py-2 font-semibold">耗时</th>
              <th className="px-3 py-2 font-semibold">备注</th>
            </tr>
          </thead>
          <tbody>
            {results.map((r) => {
              const badge = STATUS_BADGE[r.status];
              return (
                <tr key={r.id} className="border-t border-[var(--border)] hover:bg-[var(--bg-hover)]">
                  <td className="px-3 py-2 font-semibold">{r.suite}</td>
                  <td className="px-3 py-2 text-[var(--text-muted)]">{r.target}</td>
                  <td className="px-3 py-2 text-[var(--text-muted)]">{r.runAt}</td>
                  <td className="px-3 py-2"><span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${badge.className}`}><span className={`h-1.5 w-1.5 rounded-full ${badge.dot}`} aria-hidden="true" />{badge.label}</span></td>
                  <td className="px-3 py-2 tabular-nums">{r.passRate.toFixed(1)}%</td>
                  <td className="px-3 py-2 text-[var(--text-muted)]">{r.duration}</td>
                  <td className="px-3 py-2 text-[var(--text-muted)]">{r.notes}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function CaseTab({ suites }: { suites: EvalSuite[] }) {
  const withCases = suites.filter((s) => s.casesList.length > 0);
  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-teal-700 dark:text-teal-300">评测用例</p>
      <h3 className="mt-2 text-lg font-semibold">所有用例</h3>
      <p className="mt-1 text-xs text-[var(--text-muted)]">按套件汇总展示用例,在对应套件详情中可调整。</p>
      <div className="mt-5 space-y-3">
        {withCases.map((s) => (
          <article key={s.id} className="rounded-xl border border-[var(--border)] bg-[var(--surface-1)] p-4">
            <header className="flex items-center justify-between">
              <h4 className="text-sm font-semibold">{s.name}</h4>
              <span className="text-[10px] text-[var(--text-muted)]">{s.casesList.length} 条用例</span>
            </header>
            <ul className="mt-3 space-y-2">
              {s.casesList.map((c) => (
                <li key={c.id} className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] px-3 py-2 text-[11px]">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold">{c.name}</span>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${caseStatusClass(c.status)}`}>{caseStatusLabel(c.status)}</span>
                  </div>
                  <p className="mt-1 text-[var(--text-muted)]">输入:{c.input || '—'}</p>
                  <p className="mt-0.5 text-[var(--text-muted)]">期望:{c.expected || '—'}</p>
                  <p className="mt-1 text-[10px] text-[var(--text-muted)]">耗时 {c.durationMs} ms · 评分 {c.score.toFixed(1)}</p>
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
  );
}

export function TemplateTab({ templates, onAddTemplate }: { templates: CaseTemplate[]; onAddTemplate: (tpl: CaseTemplate) => void }) {
  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-teal-700 dark:text-teal-300">评测模板</p>
      <h3 className="mt-2 text-lg font-semibold">常用评测模板</h3>
      <p className="mt-1 text-xs text-[var(--text-muted)]">挑选模板一键生成评测套件,在套件详情中再调整具体配置。</p>
      <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {templates.map((tpl) => {
          const Icon = tplIconMap[tpl.icon] ?? Sparkles;
          return (
            <article key={tpl.id} className="flex flex-col rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 transition hover:border-[var(--brand)]">
              <header className="flex items-start gap-3">
                <span className={`grid h-10 w-10 place-items-center rounded-xl ${TYPE_META[tpl.type].tone}`}>
                  <Icon className="h-5 w-5" />
                </span>
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">{TYPE_META[tpl.type].label}</p>
                  <h4 className="text-sm font-semibold">{tpl.name}</h4>
                </div>
              </header>
              <p className="mt-3 text-xs leading-6 text-[var(--text-muted)]">{tpl.description}</p>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">输入示例</p>
                  <p className="mt-1 rounded-lg bg-[var(--bg-elevated)] px-2 py-1.5 text-[10px] leading-5 text-[var(--text-secondary)]">{tpl.inputExample}</p>
                </div>
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">期望示例</p>
                  <p className="mt-1 rounded-lg bg-[var(--bg-elevated)] px-2 py-1.5 text-[10px] leading-5 text-[var(--text-secondary)]">{tpl.expectedExample}</p>
                </div>
              </div>
              <ul className="mt-3 space-y-1 text-[10px] text-[var(--text-muted)]">
                {tpl.criteria.map((c, idx) => <li key={idx}>· {c}</li>)}
              </ul>
              <div className="mt-auto pt-4">
                <button type="button" onClick={() => onAddTemplate(tpl)} className="inline-flex w-full items-center justify-center gap-1.5 rounded-xl border border-[var(--brand)] bg-[var(--brand-light)] px-3 py-2 text-xs font-semibold text-[var(--brand)] hover:bg-white">
                  <Plus className="h-3.5 w-3.5" />创建套件
                </button>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

export { uid };
