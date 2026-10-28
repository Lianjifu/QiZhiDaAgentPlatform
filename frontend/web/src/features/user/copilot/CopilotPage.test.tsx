import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import Copilot from './CopilotPage';

// 附件现在**一律真上传** (演示环境也一样 —— 演示后端有真的附件端点).
// 没有会话时不能上传, 也不能再像以前那样把文件名塞进输入框假装成功.
vi.mock('@/lib/api-mode', () => ({
  runtimeConfig: () => ({ environment: 'demo', dataMode: 'demo' }),
  isDemoApiMode: () => true,
  apiBaseURL: () => '',
}));

describe('Copilot page', () => {
  afterEach(() => cleanup());

  it('refuses to fake an attachment when there is no session', async () => {
    render(
      <MemoryRouter>
        <Copilot />
      </MemoryRouter>,
    );

    const input = screen.getByPlaceholderText('描述你想完成的工作...') as HTMLTextAreaElement;
    const fileInput = document.getElementById('copilot-file-input') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [new File(['内容'], '会议纪要.pdf', { type: 'application/pdf' })] } });

    await waitFor(() => expect(screen.getByText(/请先打开会话/)).toBeTruthy());
    expect(input.value).not.toContain('会议纪要.pdf');
  });

  it('shows and dismisses slash and mention shortcut states', () => {
    render(
      <MemoryRouter>
        <Copilot />
      </MemoryRouter>,
    );

    const input = screen.getByPlaceholderText('描述你想完成的工作...') as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: '/' } });
    expect(screen.getByRole('status').textContent).toContain('快捷命令');
    fireEvent.click(screen.getByRole('option', { name: '/整理' }));
    expect(input.value).toBe('/整理 ');

    fireEvent.change(input, { target: { value: '@' } });
    expect(screen.getByRole('status').textContent).toContain('提及对象');
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('preserves the knowledge source handoff', () => {
    render(
      <MemoryRouter initialEntries={[{ pathname: '/copilot', state: { knowledgeTitle: '差旅与报销指南' } }]}>
        <Copilot />
      </MemoryRouter>,
    );

    expect((screen.getByPlaceholderText('描述你想完成的工作...') as HTMLTextAreaElement).value).toContain('差旅与报销指南');
  });
});
