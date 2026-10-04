import { useApiQuery } from '@/services/query';
import { qk } from '@/api/shared/query-keys';
import { useAuthStore } from '@/features/auth';
import type { Member, SharedItem, Team, TeamAccent } from './schema';

const ACCENTS: TeamAccent[] = ['emerald', 'sky', 'amber'];
const MEMBER_COLOR = 'bg-[var(--brand-light)] text-[var(--brand)]';

function asRecords(raw: unknown): Record<string, unknown>[] {
  if (Array.isArray(raw)) {
    return raw.filter((row): row is Record<string, unknown> => !!row && typeof row === 'object');
  }
  if (!raw || typeof raw !== 'object') return [];
  const row = raw as Record<string, unknown>;
  for (const key of ['items', 'data', 'workspaces', 'members', 'records']) {
    const nested = row[key];
    if (Array.isArray(nested)) return asRecords(nested);
  }
  if (typeof row.id === 'string' || typeof row.email === 'string' || typeof row.name === 'string' || typeof row.displayName === 'string') {
    return [row];
  }
  return [];
}

function str(row: Record<string, unknown>, ...keys: string[]): string {
  for (const key of keys) {
    const value = row[key];
    if (typeof value === 'string' && value.trim()) return value;
  }
  return '';
}

export function mapTeams(raw: unknown): Team[] {
  return asRecords(raw).map((row, index) => {
    const accentRaw = str(row, 'accent');
    const accent = ACCENTS.includes(accentRaw as TeamAccent) ? (accentRaw as TeamAccent) : ACCENTS[index % ACCENTS.length]!;
    return {
      name: str(row, 'displayName', 'display_name', 'name', 'slug') || `工作空间 ${index + 1}`,
      note: str(row, 'note', 'slug') || '当前工作空间',
      accent,
    };
  });
}

export function mapMembers(raw: unknown, fallbackTeam: string): Member[] {
  return asRecords(raw).map((row, index) => {
    const name = str(row, 'name', 'displayName', 'display_name', 'email') || `成员 ${index + 1}`;
    const color = str(row, 'color') || MEMBER_COLOR;
    return {
      id: str(row, 'id') || `member-${index}`,
      name,
      role: str(row, 'role', 'email') || '工作空间成员',
      team: str(row, 'team') || fallbackTeam,
      initials: str(row, 'initials') || name.slice(0, 1).toUpperCase(),
      color,
    };
  });
}

export function mapSharedItems(raw: unknown, team: string, kind: SharedItem['kind']): SharedItem[] {
  return asRecords(raw).map((row, index) => {
    const title = str(row, 'title', 'name') || `共享内容 ${index + 1}`;
    const kindRaw = str(row, 'kind');
    const resolvedKind: SharedItem['kind'] =
      kindRaw === 'agent' || kindRaw === 'knowledge' || kindRaw === 'output' ? kindRaw : kind;
    return {
      id: str(row, 'id') || `${kind}-${index}`,
      title,
      kind: resolvedKind,
      team: str(row, 'team') || team,
      owner: str(row, 'owner', 'displayName') || '工作空间',
      description: str(row, 'description', 'note', 'excerpt') || '',
      updated: str(row, 'updated', 'updatedAt', 'lastUpdate') || '最近更新',
      label: str(row, 'label', 'category') || (resolvedKind === 'agent' ? '智能体' : resolvedKind === 'knowledge' ? '知识' : '产出物'),
    };
  });
}

export function memberFromSession(team: string): Member | null {
  const user = useAuthStore.getState().user;
  if (!user?.id && !user?.email) return null;
  const name = user.name || user.email || '当前用户';
  return {
    id: user.id || user.email,
    name,
    role: user.role === 'admin' ? '管理员' : '工作空间成员',
    team,
    initials: name.slice(0, 1).toUpperCase(),
    color: MEMBER_COLOR,
  };
}

export function useTeams() {
  const q = useApiQuery<unknown>(
    [...qk.user.team.root, 'teams'],
    '/api/workspaces',
    undefined,
    { staleTime: 60_000, retry: false },
  );
  return { ...q, data: mapTeams(q.data) };
}

export function useMembers(teamName: string) {
  const q = useApiQuery<unknown>(
    [...qk.user.team.members],
    '/api/auth/me',
    undefined,
    { staleTime: 30_000, retry: false },
  );
  const mapped = mapMembers(q.data, teamName);
  const self = memberFromSession(teamName);
  const data = mapped.length > 0 ? mapped : self ? [{ ...self, team: teamName }] : [];
  return { ...q, data };
}

export function useSharedItems(teamName: string) {
  const agents = useApiQuery<unknown>(
    [...qk.user.team.shared, 'agents'],
    '/api/catalog/agents',
    undefined,
    { staleTime: 30_000, retry: false },
  );
  const knowledge = useApiQuery<unknown>(
    [...qk.user.team.shared, 'knowledge'],
    '/api/catalog/knowledge',
    undefined,
    { staleTime: 30_000, retry: false },
  );
  return {
    data: [
      ...mapSharedItems(agents.data, teamName, 'agent'),
      ...mapSharedItems(knowledge.data, teamName, 'knowledge'),
    ],
    isLoading: agents.isLoading || knowledge.isLoading,
    isError: agents.isError && knowledge.isError,
    error: agents.error ?? knowledge.error,
    refetch: () => {
      void agents.refetch();
      void knowledge.refetch();
    },
  };
}
