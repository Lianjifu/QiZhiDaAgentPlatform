/**
 * LoginQuickChips — 一键用开发账号登录
 */
import type { ReactNode } from 'react';

export interface LoginQuickRole {
  email: string;
  label: string;
  sub: string;
  Icon: (props: { className?: string }) => ReactNode;
}

interface LoginQuickChipsProps {
  title: string;
  roles: LoginQuickRole[];
  onChoose: (email: string) => void;
}

export function LoginQuickChips({ title, roles, onChoose }: LoginQuickChipsProps) {
  return (
    <div>
      <p className="login-kicker mb-3 text-[var(--text-muted)]">{title}</p>
      <div className="grid grid-cols-2 gap-2">
        {roles.map((r, index) => (
          <button
            key={`${r.email}-${index}`}
            type="button"
            onClick={() => onChoose(r.email)}
            title={`${r.label} · ${r.sub}`}
            className="login-demo-chip group flex items-center gap-2 border border-[var(--login-rule)] bg-transparent px-3 py-2.5 text-left transition-colors hover:border-[var(--login-blue)] hover:bg-[var(--login-blue)]/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--login-blue)]/30"
          >
            <r.Icon className="h-3.5 w-3.5 shrink-0 text-[var(--text-muted)] group-hover:text-[var(--login-orange)]" />
            <span className="min-w-0 flex-1 leading-tight">
              <span className="block truncate text-[12px] text-[var(--text)]">{r.label}</span>
              <span className="mt-0.5 block truncate text-[11px] text-[var(--text-muted)]">{r.sub}</span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
