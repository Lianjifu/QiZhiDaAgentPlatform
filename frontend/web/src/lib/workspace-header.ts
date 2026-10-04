import { useAuthStore } from '@/features/auth';
import { useWorkspaceStore } from '@/stores/workspaceStore';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function asWorkspaceId(value: string | undefined | null): string {
  const raw = (value ?? '').trim();
  return UUID_RE.test(raw) ? raw : '';
}

/** Pick a workspace id safe to send as x-workspace-id (must be in JWT membership). */
export function resolveWorkspaceHeader(): string {
  const user = useAuthStore.getState().user;
  const current = useWorkspaceStore.getState().currentWorkspaceId;
  const candidate = asWorkspaceId(current) || asWorkspaceId(user?.workspaceId);
  const allowed = (user?.workspaceIds ?? []).map((id) => asWorkspaceId(id)).filter(Boolean);
  if (allowed.length === 0) return candidate;
  if (candidate && allowed.includes(candidate)) return candidate;
  return allowed[0]!;
}
