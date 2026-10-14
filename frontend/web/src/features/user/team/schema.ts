/**
 * 用户侧「我的协作」实体 — 团队空间 + 成员 + 共享内容(智能体 / 知识 / 产出物)。
 */
export type TeamAccent = 'emerald' | 'sky' | 'amber';
export type SharedKind = 'agent' | 'knowledge' | 'output';

export interface Team {
  name: string;
  note: string;
  accent: TeamAccent;
}

export interface Member {
  id: string;
  name: string;
  role: string;
  team: string;
  initials: string;
  color: string;
}

export interface SharedItem {
  id: string;
  title: string;
  kind: SharedKind;
  team: string;
  owner: string;
  description: string;
  updated: string;
  label: string;
}

export interface InviteMemberVars {
  team: string;
  email: string;
}

export interface WorkspaceInvitation {
  id: string;
  email: string;
  role: string;
  status: 'pending';
  deliveryStatus: string;
}
