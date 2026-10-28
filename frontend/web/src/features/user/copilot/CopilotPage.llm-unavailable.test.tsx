import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import Copilot from './CopilotPage';

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

const streamError = vi.hoisted(() => ({ current: null as unknown }));

vi.mock('./copilotApi', async () => {
  const actual = await vi.importActual<typeof import('./copilotApi')>('./copilotApi');
  return {
    ...actual,
    listCopilotSessions: vi.fn(async () => []),
    createCopilotSession: vi.fn(async () => ({ id: 'sid-1', messages: [] })),
    loadCopilotSession: vi.fn(async () => ({ id: 'sid-1', messages: [] })),
    streamCopilotTurn: vi.fn(async () => {
      throw streamError.current;
    }),
  };
});

/** 后端 ApiError 的形状 —— 带 status, 文案里的括号是全角的. */
function apiError(status: number, message: string) {
  const err = new Error(message) as Error & { status?: number; code?: string };
  err.status = status;
  err.code = 'E_STREAM';
  return err;
}

describe('Copilot LLM 未配置提示', () => {
  afterEach(() => {
    cleanup();
    streamError.current = null;
  });

  it('把 503 翻译成"未配置 LLM 供应商"引导语, 而不是原始报错', async () => {
    // 这条文案就是 packages/api 里 streamEvents 抛的: 括号是全角的,
    // 所以靠正则匹配 "(HTTP 503)" 是匹配不上的 —— 只能看 status.
    streamError.current = apiError(503, '流式请求失败（HTTP 503）');

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
      expect(screen.getByText(/未配置 LLM 供应商/)).toBeTruthy();
    });
    expect(screen.queryByText(/流式请求失败/)).toBeNull();
  });

  it('非 503 的错误原样透出', async () => {
    streamError.current = apiError(400, '请求体不合法');

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
      expect(screen.getByText(/请求体不合法/)).toBeTruthy();
    });
  });
});
