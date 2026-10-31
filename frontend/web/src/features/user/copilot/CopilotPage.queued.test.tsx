import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import Copilot from './CopilotPage';

// jsdom 没有实现 scrollIntoView —— 页面滚动到底的 effect 会调用它.
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

/**
 * **排队中** —— 同会话严格排队时后端会发 `queued` 块 ✓。
 *
 * ⚠️ **不显示的话用户只看到转圈** ✗✗（Router 方案 §0.7 ✓）——
 * 所以前端必须消费这一块 ✓。
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
        onEvent('queued', { position: 2, waited_ms: 1200, estimated_wait_seconds: 3 });
        onEvent('message', { content: '这是回答' });
        onEvent('done', { final_message: '这是回答' });
      },
    ),
  };
});

describe('Copilot queued chunk', () => {
  afterEach(() => cleanup());

  it('tells the user the turn is waiting in the queue', async () => {
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
      expect(screen.getByText(/排队中/)).toBeTruthy();
    });
    expect(screen.getByText(/第 2 位/)).toBeTruthy();
  });
});
