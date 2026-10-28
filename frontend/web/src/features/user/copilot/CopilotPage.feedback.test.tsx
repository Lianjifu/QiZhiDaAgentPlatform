import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import Copilot from './CopilotPage';

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

const submitted: Array<{ rating: number }> = [];

vi.mock('./copilotApi', async () => {
  const actual = await vi.importActual<typeof import('./copilotApi')>('./copilotApi');
  return {
    ...actual,
    listCopilotSessions: vi.fn(async () => []),
    createCopilotSession: vi.fn(async () => ({ id: 'sid-1', messages: [] })),
    loadCopilotSession: vi.fn(async () => ({ id: 'sid-1', messages: [] })),
    submitCopilotFeedback: vi.fn(async (_sid: string, rating: number) => {
      submitted.push({ rating });
    }),
    streamCopilotTurn: vi.fn(
      async (
        _sessionId: string,
        _content: string,
        onEvent: (event: string, data: Record<string, unknown>) => void,
      ) => {
        onEvent('message', { content: '回答内容' });
        onEvent('done', { final_message: '回答内容' });
      },
    ),
  };
});

describe('Copilot feedback', () => {
  afterEach(() => {
    cleanup();
    submitted.length = 0;
  });

  it('posts a thumbs-up for the assistant answer', async () => {
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

    const up = await screen.findByRole('button', { name: '这条回答有帮助' });
    fireEvent.click(up);

    await waitFor(() => {
      expect(submitted).toEqual([{ rating: 5 }]);
    });
  });
});
