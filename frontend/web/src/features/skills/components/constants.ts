/**
 * 管理侧技能页常量 — 从原 AdminSkills.tsx 抽出,保持视觉与交互不变。
 */
import {
  BookOpen, CirclePlay, FileCode, FileJson, GitBranch, History, Layers,
  Network, ShieldAlert, ShieldCheck, ShieldQuestion, Sparkles, Wrench,
  type LucideIcon,
} from 'lucide-react';
import type {
  SkillType, SkillStatus, RiskLevel, SkillSortKey,
  SkillExportFormat, SkillExportField,
} from '../schema';

export type DrawerPanel = 'basic' | 'schema' | 'permission' | 'runtime' | 'versions' | 'monitor' | 'agents' | 'audit';

export const TYPE_META: Record<SkillType, { icon: LucideIcon; tone: string; label: string; subLabel: string; description: string }> = {
  Skill: { icon: Sparkles, tone: 'bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300', label: '技能', subLabel: 'Skill', description: '把经验、流程或模板沉淀成可复用能力' },
  Tool: { icon: Wrench, tone: 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300', label: '技能', subLabel: 'Tool', description: '执行具体动作,通常涉及外部系统' },
  MCP: { icon: Network, tone: 'bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300', label: '技能', subLabel: 'MCP', description: '通过 MCP 协议接入第三方服务' },
};

export const STATUS_BADGE: Record<SkillStatus, { label: string; className: string; dot: string }> = {
  draft: { label: '草稿', className: 'bg-[var(--bg-elevated)] text-[var(--text-secondary)]', dot: 'bg-[var(--text-muted)]' },
  graying: { label: '灰度中', className: 'bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300', dot: 'bg-sky-500' },
  published: { label: '已发布', className: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300', dot: 'bg-emerald-500' },
  retired: { label: '已下线', className: 'bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300', dot: 'bg-rose-500' },
};

export const RISK_BADGE: Record<RiskLevel, { label: string; className: string; icon: LucideIcon }> = {
  low: { label: '低风险', className: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300', icon: ShieldCheck },
  medium: { label: '中等风险', className: 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300', icon: ShieldQuestion },
  high: { label: '高风险', className: 'bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300', icon: ShieldAlert },
};

export const SORT_OPTIONS: Array<{ id: SkillSortKey; label: string }> = [
  { id: 'updated', label: '最近更新' },
  { id: 'calls', label: '调用量' },
  { id: 'name', label: '名称' },
];

export const STATUS_OPTIONS: Array<{ id: 'all' | SkillStatus; label: string }> = [
  { id: 'all', label: '全部状态' },
  { id: 'published', label: '已发布' },
  { id: 'draft', label: '草稿' },
  { id: 'graying', label: '灰度中' },
  { id: 'retired', label: '已下线' },
];

export const TYPE_FILTER_OPTIONS: Array<{ id: 'all' | SkillType; label: string }> = [
  { id: 'all', label: '全部类型' },
  { id: 'Skill', label: 'Skill' },
  { id: 'Tool', label: 'Tool' },
  { id: 'MCP', label: 'MCP' },
];

export const EXCHANGE_FORMATS: Array<{ id: SkillExportFormat; label: string; description: string; icon: LucideIcon }> = [
  { id: 'json', label: 'JSON', description: '结构化数组,字段一一映射', icon: FileJson },
  { id: 'yaml', label: 'YAML', description: '缩进式清单,支持嵌套字段', icon: FileCode },
];

export const EXCHANGE_FIELDS: Array<{ id: SkillExportField; label: string }> = [
  { id: 'meta', label: '元信息' },
  { id: 'schema', label: '输入输出' },
  { id: 'permission', label: '风险与权限' },
  { id: 'version', label: '版本信息' },
];

export const DRAWER_NAV_ITEMS: Array<{ id: DrawerPanel; label: string; icon: LucideIcon }> = [
  { id: 'basic', label: '基本信息', icon: BookOpen },
  { id: 'schema', label: '输入输出', icon: Layers },
  { id: 'permission', label: '风险与权限', icon: ShieldCheck },
  { id: 'versions', label: '版本历史', icon: GitBranch },
  { id: 'monitor', label: '调用监控', icon: CirclePlay },
  { id: 'agents', label: '关联智能体', icon: Sparkles },
  { id: 'audit', label: '审计日志', icon: History },
];

export const DEFAULT_EXCHANGE_FIELDS: Record<SkillExportField, boolean> = {
  meta: true,
  schema: true,
  permission: true,
  version: false,
};

export function formatCalls(value: number): string {
  if (value === 0) return '—';
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`;
  return value.toString();
}

export function uid(prefix: string) {
  return `${prefix}-${Math.random().toString(36).slice(2, 8)}`;
}

export function getLifecycleCounts(list: Array<{ status: SkillStatus; calls: number }>) {
  return {
    total: list.length,
    published: list.filter((s) => s.status === 'published').length,
    draft: list.filter((s) => s.status === 'draft').length,
    graying: list.filter((s) => s.status === 'graying').length,
    retired: list.filter((s) => s.status === 'retired').length,
    calls: list.reduce((sum, s) => sum + s.calls, 0),
  };
}