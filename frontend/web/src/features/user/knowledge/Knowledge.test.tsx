import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import Knowledge from '@/features/user/knowledge';
import Copilot from '@/features/user/copilot';
import { mockKbs, mockDocs } from '@/features/knowledge/fixtures';
import { projectKnowledgeDocs } from '@/features/user/catalog/mappers';
import { qk } from '@/api/shared/query-keys';

const CHOSEN_STORAGE_KEY = 'qzdap.user.knowledge.chosen';

afterEach(() => cleanup());
beforeEach(() => sessionStorage.removeItem(CHOSEN_STORAGE_KEY));

function renderKnowledge(chosen: string[] = []) {
  if (chosen.length) sessionStorage.setItem(CHOSEN_STORAGE_KEY, JSON.stringify(chosen));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData([...qk.user.knowledge.list, {}, 'w1'], projectKnowledgeDocs(mockKbs, mockDocs));
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/knowledge']}>
        <Routes>
          <Route path="/knowledge" element={<Knowledge />} />
          <Route path="/copilot" element={<Copilot />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('知识 · 浏览资料', () => {
  it('opens browse drawer from admin knowledge and adds to my knowledge', () => {
    renderKnowledge();
    expect(screen.getByRole('heading', { name: '知识' })).toBeTruthy();
    expect(screen.getByText('还没有知识')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: '浏览资料' }));
    const drawer = screen.getByRole('dialog', { name: '浏览并选用资料' });
    expect(within(drawer).getByText('差旅报销指南.md')).toBeTruthy();
    expect(within(drawer).queryByText('信息安全等级保护指南.pdf')).toBeNull();

    const row = within(drawer).getByText('差旅报销指南.md').closest('li') as HTMLElement;
    fireEvent.click(within(row).getByRole('button', { name: '加入知识' }));
    fireEvent.click(within(drawer).getByRole('button', { name: '完成' }));

    expect(screen.queryByRole('dialog', { name: '浏览并选用资料' })).toBeNull();
    expect(screen.getAllByText('差旅报销指南.md').length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: '移出差旅报销指南.md' }));
    expect(screen.getByText('还没有知识')).toBeTruthy();
  });

  it('starts copilot from browse drawer with knowledge context', () => {
    renderKnowledge();
    fireEvent.click(screen.getByRole('button', { name: '浏览资料' }));
    const drawer = screen.getByRole('dialog', { name: '浏览并选用资料' });
    const row = within(drawer).getByText('产品手册 v3.pdf').closest('li') as HTMLElement;
    fireEvent.click(within(row).getByRole('button', { name: '带入对话' }));
    expect(screen.getByDisplayValue(/请基于《产品手册 v3.pdf》/)).toBeTruthy();
  });
});
