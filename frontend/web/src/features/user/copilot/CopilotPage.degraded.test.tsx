import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import Copilot from './CopilotPage';

// jsdom 没有实现 scrollIntoView —— 页面滚动到底的 effect 会调用它.
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

/**
 * 降级标记 —— 后端每一块都带 `flags`，用户要看得见。
 *
 * ⚠️ **降级时的回答是不完整的** ✓ —— 不说就是骗 ✓。
 */
vi.mock('./copilotApi', async () => {
  const actual = await vi.importActual<typeof import('./copilotApi')>('./copilotApi');
  return {
    ...actual,
    listCopilotSessions: vi.fn(async () => []),
    createCopilotSession: vi.fn(async () => ({ id: 'sid-1', messages: [] })),
    loadCopilotSession: vi.fn(async () => ({ id: 'sid-1', messages: [] })),
    streamCopilotTurn: vi.fn(
      async (
        _sessionId: string,
        _content: string,
        onEvent: (event: string, data: Record<string, unknown>) => void,
      ) => {
        onEvent('message', { content: '这是回答', flags: ['recall_degraded'] });
        onEvent('done', { final_message: '这是回答', flags: ['recall_degraded'] });
      },
    ),
  };
});

describe('Copilot degraded flags', () => {
  afterEach(() => cleanup());

  it('tells the user when the turn ran degraded', async () => {
    render(
      <MemoryRouter
        initialEntries={[{ pathname: '/copilot', state: { agentId: 'agent-1', agentName: 'A' } }]}
      >
        <Copilot />
      </MemoryRouter>,
    );

    const input = screen.getByPlaceholderText('描述你想完成的工作...') as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: 'hi' } });
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }));

    await waitFor(() => {
      expect(screen.getByText(/知识召回降级/)).toBeTruthy();
    });
    expect(screen.getByText(/回答可能不完整/)).toBeTruthy();
  });
});
