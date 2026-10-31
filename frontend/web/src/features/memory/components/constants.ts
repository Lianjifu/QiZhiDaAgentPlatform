/**
 * AdminMemory 常量 — TABS / L1/L2/L3 状态徽章 / 类别 / layer meta / 色板。
 */
import { BookOpen, Brain, type LucideIcon, Zap } from 'lucide-react';
import type {
  EvictionStrategy, L1Status, L2Category, L2Status, L3Status, MemoryLayer, MemoryRange, MemoryTabId, Tone,
} from '../schema';

export const TABS: Array<{ id: MemoryTabId; label: string; icon: LucideIcon }> = [
  { id: 'l1', label: '短期记忆', icon: Zap },
  { id: 'l2', label: '长期记忆', icon: Brain },
  { id: 'l3', label: '知识记忆', icon: BookOpen },
];

export const RANGES: MemoryRange[] = ['7d', '30d', '90d'];
export const RANGE_LABEL: Record<MemoryRange, string> = { '7d': '最近 7 天', '30d': '最近 30 天', '90d': '最近 90 天' };

export const L1_STATUS_BADGE: Record<L1Status, { label: string; className: string }> = {
  active: { label: '活跃', className: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300' },
  paused: { label: '已暂停', className: 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-200' },
  expired: { label: '已过期', className: 'bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300' },
};

export const L2_STATUS_BADGE: Record<L2Status, { label: string; className: string }> = {
  pending: { label: '待确认', className: 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300' },
  confirmed: { label: '已确认', className: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300' },
  retired: { label: '已下线', className: 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-200' },
};

export const L2_CATEGORY_LABEL: Record<L2Category, string> = {
  preference: '偏好', fact: '事实', style: '风格', context: '上下文',
};

export const L3_STATUS_BADGE: Record<L3Status, { label: string; className: string }> = {
  draft: { label: '草稿', className: 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300' },
  published: { label: '已发布', className: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300' },
  retired: { label: '已下线', className: 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-200' },
};

export const LAYER_META: Record<MemoryLayer, { label: string; tone: Tone; icon: LucideIcon; tagline: string; policyLabel?: string }> = {
  // ⚠️ **L1 没有保留策略了** ✓ —— 表退役了 ✓（决策 #5 ✓ —— M-46 ✓）。
  l1: { label: '短期记忆', tone: 'info', icon: Zap, tagline: '当前会话上下文,会话结束 TTL 到期后清理' },
  l2: { label: '长期记忆', tone: 'purple', icon: Brain, tagline: '跨会话保留的用户偏好与事实', policyLabel: '长期记忆' },
  // ⚠️ **L3 没有保留策略了** ✓ —— 表退役了 ✓（决策 #1 ✓ —— M-47 ✓）→
  // 团队知识的保留归 **knowledge** ✓。
  l3: { label: '知识记忆', tone: 'brand', icon: BookOpen, tagline: '团队级共享知识,所有智能体可检索' },
};

export const toneClass: Record<Tone, string> = {
  brand: 'bg-blue-50 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300',
  info: 'bg-sky-50 text-sky-600 dark:bg-sky-500/15 dark:text-sky-300',
  success: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-300',
  warn: 'bg-amber-50 text-amber-600 dark:bg-amber-500/15 dark:text-amber-300',
  danger: 'bg-rose-50 text-rose-600 dark:bg-rose-500/15 dark:text-rose-300',
  purple: 'bg-violet-50 text-violet-600 dark:bg-violet-500/15 dark:text-violet-300',
};

export const EVICTION_LABEL: Record<EvictionStrategy, string> = {
  lru: 'LRU · 最近最少使用',
  fifo: 'FIFO · 先进先出',
  confidence: 'Confidence · 低置信度优先',
};

export function ttlLabel(ttlMinutes: number): string {
  if (ttlMinutes < 1440) return `${ttlMinutes} 分钟`;
  if (ttlMinutes < 1440 * 30) return `${Math.round(ttlMinutes / 1440)} 天`;
  return `${Math.round(ttlMinutes / (1440 * 30))} 月`;
}