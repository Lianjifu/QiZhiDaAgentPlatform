/**
 * 用户侧「资源库」的归一形状 ✓。
 *
 * ⚠️ **为什么要有这一层** ✓ —— 智能体 / 知识 / 技能 / 工作流四类资源的
 * 原始字段各不一样 ✓（``useCase`` / ``tags`` / ``risk`` / ``steps`` ✓），
 * 但**页面骨架完全一样** ✓（列表 ✓ + 卡片 ✓ + 详情抽屉 ✓ + 浏览抽屉 ✓）。
 * 这一层把它们**投影成同一种形状** ✓ —— 骨架只写一遍 ✓。
 *
 * ⚠️ **投影是「只读视图」** ✓ —— 动作（收藏 ✓ / 选用 ✓ / 发起对话 ✓）由
 * 各自的 kind 组件持有 ✓（它们知道原始类型 ✓）。
 */

import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';

export type ResourceKindKey = 'agents' | 'knowledge' | 'skills' | 'automations';

export interface ResourceField {
  label: string;
  value: string;
}

export interface ResourceItem {
  id: string;
  name: string;
  description: string;
  /** 卡片上的一行小字 ✓ —— 「场景 · 负责人」这类 ✓ */
  meta: string;
  /** **浏览抽屉的筛选值** ✓ —— `{ '场景': '销售支持' }` ✓（按标签名取 ✓） */
  filters?: Record<string, string>;
  /** 图标底色 ✓（tailwind 类名 ✓ —— 与管理端同口径 ✓） */
  tone: string;
  icon: LucideIcon;
  /** 右上角角标 ✓ —— 「可使用」/「暂不可用」这类 ✓ */
  badge?: { label: string; tone: 'ok' | 'muted' };
  /** 详情抽屉的字段对 ✓ */
  fields: ResourceField[];
  /** 详情抽屉的补充段落 ✓ */
  note?: string;
  /** **详情抽屉的额外内容** ✓ —— 只有某一类资源才有 ✓（例：能力的风险提示 ✓） */
  extra?: ReactNode;
  /** **详情抽屉的额外按钮** ✓ —— 例：知识条目的「复制引用」✓ */
  extraActions?: { label: string; onClick: () => void }[];
  /** 卡片主行动 ✓（按钮文案 + 禁用 + 执行体 ✓） */
  primary: {
    label: string;
    /** **按钮的无障碍名** ✓ —— 「与 XX 开始对话」这类 ✓（同名按钮要能区分 ✓） */
    ariaLabel?: string;
    icon?: LucideIcon;
    disabled?: boolean;
    run: () => void;
  };
}

/** **抽屉的文案** ✓ —— 每类资源各说各的 ✓（不共用一套空话 ✓）。 */
export interface ResourceCopy {
  /** 抽屉眉标 ✓ */
  eyebrow: string;
  /** **详情抽屉的无障碍名后缀** ✓ —— 「工作流详情」/「详情」这类 ✓ */
  detailSuffix?: string;
  /** 浏览抽屉的标题与说明 ✓ */
  browseTitle: string;
  browseDescription: string;
  /** 「选用」按钮的落地提示 ✓ */
  chosenHint: string;
  /** 目录为空时的提示 ✓ */
  emptyTitle: string;
  emptyDescription: string;
}
