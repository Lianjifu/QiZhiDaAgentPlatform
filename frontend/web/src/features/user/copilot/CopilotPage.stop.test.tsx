import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import Copilot from './CopilotPage';

// jsdom 没有实现 scrollIntoView —— 页面滚动到底的 effect 会调用它.
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

/**
 * 停止生成 —— 前端断流 + 后端收尾.
 *
 * 这里 mock 掉 copilotApi 的流式调用, 让它停在一个可控的「永不结束」的
 * promise 上, 从而能观察到 sending 状态下的停止按钮.
 */
const stream = {
  release: null as null | (() => void),
  aborted: false,
};

vi.mock('./copilotApi', async () => {
  const actual = await vi.importActual<typeof import('./copilotApi')>('./copilotApi');
  return {
    ...actual,
    listCopilotSessions: vi.fn(async () => []),
    createCopilotSession: vi.fn(async () => ({ id: 'sid-1', messages: [] })),
    loadCopilotSession: vi.fn(async () => ({ id: 'sid-1', messages: [] })),
    cancelCopilotTurn: vi.fn(async () => ({ ok: true, cancelled: true })),
    streamCopilotTurn: vi.fn(
      async (
        _sessionId: string,
        _content: string,
        onEvent: (event: string, data: Record<string, unknown>) => void,
        signal?: AbortSignal,
      ) => {
        onEvent('message', { content: 'partial' });
        await new Promise<void>((resolve, reject) => {
          stream.release = resolve;
          // 真实 fetch 在 abort 时会 reject —— 这里保持同样的语义.
          signal?.addEventListener('abort', () => {
            stream.aborted = true;
            reject(new DOMException('Aborted', 'AbortError'));
          });
        });
        onEvent('done', { final_message: 'partial' });
      },
    ),
  };
});

describe('Copilot stop control', () => {
  afterEach(() => {
    cleanup();
    stream.release = null;
    stream.aborted = false;
  });

  it('swaps send for stop while a turn is running, and stop aborts the stream', async () => {
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

    const stop = await screen.findByRole('button', { name: '停止生成' });
    expect(stop).toBeTruthy();

    fireEvent.click(stop);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '发送消息' })).toBeTruthy();
    });
    expect(stream.aborted).toBe(true);
  });
});
