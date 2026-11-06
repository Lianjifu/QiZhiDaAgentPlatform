import {
  Bot,
  Brain,
  Boxes,
  Beaker,
  CircleDollarSign,
  CloudCog,
  FileText,
  Gauge,
  History,
  LineChart,
  ListTodo,
  Megaphone,
  MessagesSquare,
  ScrollText,
  Settings2,
  ShieldAlert,
  Sparkles,
  ThumbsUp,
  Workflow,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

export interface NavigationItem {
  label: string;
  href: string;
  icon: LucideIcon;
  description: string;
}

export interface NavigationSection {
  title: string;
  items: NavigationItem[];
}

export const workspaceNavigation: NavigationItem[] = [
  { label: '首页', href: '/home', icon: Gauge, description: '查看今天需要处理的事项' },
  { label: '对话', href: '/copilot', icon: MessagesSquare, description: '发起对话并跟进执行结果' },
  // ⚠️ **资源库** ✓ —— 智能体 / 知识 / 技能 / 工作流合到一页 ✓（四页骨架一样 ✓）。
  { label: '资源库', href: '/library', icon: Boxes, description: '选用智能体、知识、技能与工作流' },
  { label: '任务', href: '/tasks', icon: ListTodo, description: '查看待处理、执行中和已完成的工作' },
];

export const utilityNavigation: NavigationItem[] = [
  { label: '设置', href: '/account', icon: Settings2, description: '管理用户信息、账号安全与偏好' },
];

export const adminUtilityNavigation: NavigationItem[] = [
  { label: '平台设置', href: '/admin/settings', icon: Settings2, description: '配置品牌、合规、审计与成员管理' },
];

export const adminNavigationSections: NavigationSection[] = [
  { title: '运营总览', items: [
    { label: '运营概览', href: '/admin/overview', icon: Sparkles, description: '查看平台健康、异常和建议动作' },
  ] },
  { title: '能力建设', items: [
    { label: '智能体管理', href: '/admin/agents', icon: Bot, description: '创建、评测和发布企业智能体' },
    { label: '技能管理', href: '/admin/tools', icon: Boxes, description: '管理 Skill / Tool / MCP 等技能能力' },
    { label: '知识管理', href: '/admin/knowledge', icon: FileText, description: '管理知识库、资料来源和访问权限' },
    { label: '记忆管理', href: '/admin/memory', icon: Brain, description: '管理智能体记忆、用户偏好与跨会话上下文' },
    { label: '工作流管理', href: '/admin/workflows', icon: Workflow, description: '设计、发布和分析自动化流程' },
  ] },
  { title: '平台治理', items: [
    { label: '模型配置', href: '/admin/models', icon: CloudCog, description: '配置模型服务、路由策略与健康监控' },
    { label: '额度管理', href: '/admin/quotas', icon: CircleDollarSign, description: '管理企业用量、预算与成本执行' },
    { label: '渠道配置', href: '/admin/notifications', icon: Megaphone, description: '对接飞书、企业微信、钉钉与 Web 对话入口' },
  ] },
  { title: '质量保障', items: [
    { label: '评测中心', href: '/admin/evaluations', icon: Beaker, description: '评测智能体、知识与流程的质量与对比' },
    { label: '回归追踪', href: '/admin/regressions', icon: History, description: '版本变更后自动跑回归用例，发现质量退化' },
    { label: '用户反馈', href: '/admin/feedback', icon: ThumbsUp, description: '收集用户对智能体回答的赞踩与修正建议' },
  ] },
  { title: '可观测', items: [
    { label: '工具审计', href: '/admin/tool-audit', icon: ShieldAlert, description: '工具风险：追踪工具调用、权限越界与异常敏感操作' },
    { label: '运行指标', href: '/admin/metrics', icon: LineChart, description: '成本效率：可用率、延迟、Token 与成本等关键指标' },
  ] },
];
