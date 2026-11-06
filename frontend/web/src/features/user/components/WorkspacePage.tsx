import type { ReactNode } from 'react';
import { AdminPage } from '@/components/feedback/AdminPage';

export function WorkspacePage({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <AdminPage pageClass={className}>{children}</AdminPage>
  );
}
