import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import Copilot from './CopilotPage';

describe('Copilot page', () => {
  afterEach(() => cleanup());

  it('writes the selected attachment filename into the composer', () => {
    render(
      <MemoryRouter>
        <Copilot />
      </MemoryRouter>,
    );

    const input = screen.getByPlaceholderText('描述你想完成的工作...') as HTMLTextAreaElement;
    const fileInput = document.getElementById('copilot-file-input') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [new File(['内容'], '会议纪要.pdf', { type: 'application/pdf' })] } });

    expect(input.value).toContain('[附件: 会议纪要.pdf]');
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
