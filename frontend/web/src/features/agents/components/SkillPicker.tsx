/**
 * SkillPicker — 包装 ResourcePicker,接 useAdminSkills。
 *
 * 用法:
 *   <SkillPicker selectedIds={...} onChange={ids => ...} />
 *   <SkillPicker selectedIds={...} onChange={...} allowedTypes={['Skill', 'Tool']} />  ← 排除 MCP
 */
import { useMemo } from 'react';
import { Database, Sparkles, Wrench } from 'lucide-react';
import type { RiskLevel, SchemaField, Skill, SkillType } from '@/features/skills/schema';
import { RISK_BADGE, TYPE_META } from '@/features/skills/components/constants';
import { useAdminSkills } from '@/features/skills/useAdminSkills';
import { ResourcePicker } from './ResourcePicker';

const TYPE_ICON: Record<SkillType, typeof Sparkles> = {
  Skill: Sparkles,
  Tool: Wrench,
  MCP: Database,
};

const RISK_LABEL: Record<RiskLevel, string> = {
  low: '低风险',
  medium: '中等风险',
  high: '高风险',
};

interface SkillPickerProps {
  selectedIds: string[];
  onChange: (ids: string[]) => void;
  allowedTypes?: SkillType[];
  className?: string;
  showPreview?: boolean;
  emptyText?: string;
}

export function SkillPicker({
  selectedIds,
  onChange,
  allowedTypes,
  className,
  showPreview = true,
  emptyText = '暂无可用能力,先去「技能管理」添加',
}: SkillPickerProps) {
  const { data: skills, isLoading, error } = useAdminSkills();
  const filteredSkills = useMemo(() => {
    if (!skills) return undefined;
    if (!allowedTypes || allowedTypes.length === 0) return skills;
    const set = new Set(allowedTypes);
    return skills.filter((s) => set.has(s.type));
  }, [skills, allowedTypes]);

  return (
    <ResourcePicker<Skill>
      mode="multi"
      data={filteredSkills}
      isLoading={isLoading}
      error={error}
      queryKey="skills"
      selectedIds={selectedIds}
      onChange={onChange}
      searchFields={(s) => [s.name, s.description, ...(s.tags ?? [])]}
      filterChips={[
        { key: 'Skill', label: 'Skill', match: (s) => s.type === 'Skill' },
        { key: 'Tool',  label: 'Tool',  match: (s) => s.type === 'Tool' },
        { key: 'MCP',   label: 'MCP',   match: (s) => s.type === 'MCP' },
        { key: 'low',    label: '低风险', match: (s) => s.risk === 'low' },
        { key: 'medium', label: '中等风险', match: (s) => s.risk === 'medium' },
        { key: 'high',   label: '高风险', match: (s) => s.risk === 'high' },
      ]}
      renderItem={(s, selected) => <SkillItem skill={s} selected={selected} />}
      renderPreview={showPreview ? (s) => <SkillPreview skill={s} /> : undefined}
      emptyText={emptyText}
      placeholder="搜索能力名 / 描述 / 标签"
      className={className}
    />
  );
}

function SkillItem({ skill, selected }: { skill: Skill; selected: boolean }) {
  const Icon = TYPE_ICON[skill.type] ?? Sparkles;
  const meta = TYPE_META[skill.type];
  const risk = RISK_BADGE[skill.risk];
  const RiskIcon = risk.icon;
  return (
    <div className="flex min-w-0 items-center gap-2">
      <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-md ${meta.tone}`}>
        <Icon className="h-3.5 w-3.5" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className={`truncate text-xs font-semibold ${selected ? 'text-[var(--brand)]' : 'text-[var(--text)]'}`}>
            {skill.name}
          </span>
          <span className="shrink-0 rounded-full bg-[var(--bg-elevated)] px-1.5 py-px text-[9px] font-medium uppercase tracking-wide text-[var(--text-muted)]">
            {skill.type}
          </span>
          {skill.risk !== 'low' && (
            <span className={`inline-flex shrink-0 items-center gap-0.5 rounded-full px-1.5 py-px text-[9px] font-medium ${risk.className}`}>
              <RiskIcon className="h-2.5 w-2.5" />
              {skill.risk === 'medium' ? '中' : '高'}
            </span>
          )}
        </div>
        {skill.description && (
          <p className="mt-0.5 line-clamp-1 text-[10px] text-[var(--text-muted)]">
            {skill.description}
          </p>
        )}
      </div>
    </div>
  );
}

function SkillPreview({ skill }: { skill: Skill }) {
  const meta = TYPE_META[skill.type];
  const Icon = TYPE_ICON[skill.type] ?? Sparkles;
  const risk = RISK_BADGE[skill.risk];
  const RiskIcon = risk.icon;
  return (
    <div className="space-y-3 text-xs">
      <header>
        <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">
          {meta.subLabel} · {meta.label}
        </p>
        <h3 className="mt-1 flex items-center gap-1.5 text-sm font-semibold text-[var(--text)]">
          <span className={`grid h-5 w-5 place-items-center rounded ${meta.tone}`}>
            <Icon className="h-3 w-3" />
          </span>
          {skill.name}
        </h3>
        <p className="mt-1 text-[10px] text-[var(--text-muted)]">
          {skill.description || '(无描述)'}
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-1.5">
        <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${risk.className}`}>
          <RiskIcon className="h-3 w-3" />
          {RISK_LABEL[skill.risk]}
        </span>
        {skill.needConfirm && (
          <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700">
            需确认
          </span>
        )}
        {skill.tags.map((t) => (
          <span key={t} className="rounded-full border border-[var(--border)] px-2 py-0.5 text-[10px] text-[var(--text-muted)]">#{t}</span>
        ))}
      </div>

      {skill.inputSchema.length > 0 && (
        <FieldSection label="输入" fields={skill.inputSchema} />
      )}
      {skill.outputSchema.length > 0 && (
        <FieldSection label="输出" fields={skill.outputSchema} />
      )}
      {skill.inputSchema.length === 0 && skill.outputSchema.length === 0 && (
        <p className="rounded-lg bg-[var(--bg-elevated)] p-2.5 text-[11px] text-[var(--text-muted)]">
          尚未声明输入输出字段
        </p>
      )}
    </div>
  );
}

function FieldSection({ label, fields }: { label: string; fields: SchemaField[] }) {
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">{label}</p>
      <ul className="mt-1 space-y-0.5">
        {fields.slice(0, 4).map((f) => (
          <li key={f.name} className="flex items-center gap-1 text-[10px]">
            <span className="font-mono font-semibold">{f.name}</span>
            <span className="text-[var(--text-muted)]">:{f.type}</span>
            {f.required && <span className="text-rose-500">*</span>}
            {f.description && <span className="truncate text-[var(--text-muted)]">— {f.description}</span>}
          </li>
        ))}
        {fields.length > 4 && (
          <li className="text-[10px] text-[var(--text-muted)]">…等 {fields.length - 4} 项</li>
        )}
      </ul>
    </div>
  );
}
