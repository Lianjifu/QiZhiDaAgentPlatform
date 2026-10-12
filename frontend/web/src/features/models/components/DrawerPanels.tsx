import type { Model } from '../schema';
import { TASK_LABEL, TIER_LABEL } from './constants';

interface DrawerPanelsProps {
  model: Model;
  routes: unknown[];
  onChange: (patch: Partial<Model>) => void;
}

export function DrawerPanelDetail({ model, onChange }: { model: Model; onChange: (p: Partial<Model>) => void }) {
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="模型名称">
          <input value={model.name} onChange={(e) => onChange({ name: e.target.value })} className="h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none focus:border-[var(--brand)]" />
        </Field>
        <Field label="提供商">
          <input value={model.providerName} readOnly className="h-10 w-full rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] px-3 text-sm text-[var(--text-muted)]" />
        </Field>
        <Field label="能力">
          <div className="flex flex-wrap gap-1.5">
            {model.task.map((t) => (
              <span key={t} className="inline-flex items-center gap-1 rounded-full bg-[var(--brand-light)] px-2 py-0.5 text-[10px] font-semibold text-[var(--brand)]">{TASK_LABEL[t]}</span>
            ))}
          </div>
        </Field>
        <Field label="层级">
          <select value={model.tier} onChange={(e) => onChange({ tier: e.target.value as Model['tier'] })} className="h-10 w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 text-sm outline-none">
            {(Object.keys(TIER_LABEL) as Array<keyof typeof TIER_LABEL>).map((t) => <option key={t} value={t}>{TIER_LABEL[t]}</option>)}
          </select>
        </Field>
      </div>
      <Field label="描述">
        <textarea value={model.description} onChange={(e) => onChange({ description: e.target.value })} rows={3} className="w-full rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 py-2 text-sm outline-none focus:border-[var(--brand)]" />
      </Field>
      <Field label="标签">
        <div className="flex flex-wrap gap-1.5">
          {model.tags.length === 0 ? (
            <p className="text-[11px] text-[var(--text-muted)]">无标签</p>
          ) : model.tags.map((t) => (
            <span key={t} className="inline-flex items-center gap-1 rounded-full bg-[var(--bg-elevated)] px-2 py-0.5 text-[10px] font-medium">{t}</span>
          ))}
        </div>
      </Field>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">{label}</label>
      <div className="mt-1.5">{children}</div>
    </div>
  );
}
