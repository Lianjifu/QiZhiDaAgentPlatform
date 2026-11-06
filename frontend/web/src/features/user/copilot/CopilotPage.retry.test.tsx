import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import Copilot from './CopilotPage';

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

/**
 * **失败的那一轮可以重试** ✓。
 *
 * ⚠️ 以前失败只是页面顶部飘一行黄字 ✗✗ —— 不知道是**哪一轮**坏了 ✗✗，
 * 也没法重试 ✗✗。现在失败卡片**长在那一轮里** ✓，带**重试** ✓。
 */
const streamCalls = vi.hoisted(() => ({ count: 0 }));

vi.mock('./copilotApi', async () => {
  const actual = await vi.importActual<typeof import('./copilotApi')>('./copilotApi');
  return {
    ...actual,
    listCopilotSessions: vi.fn(async () => []),
    createCopilotSession: vi.fn(async () => ({ id: 'sid-1', messages: [] })),
    loadCopilotSession: vi.fn(async () => ({ id: 'sid-1', messages: [] })),
    streamCopilotTurn: vi.fn(async () => {
      streamCalls.count += 1;
      throw new Error('后端炸了');
    }),
  };
});

describe('Copilot 失败与重试', () => {
  afterEach(() => {
    cleanup();
    streamCalls.count = 0;
  });

  it('失败落在那一轮里, 并且能重试', async () => {
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

    // ⚠️ **失败卡片长在这一轮里** ✓ —— 不是页面顶部飘一行字 ✓。
    await screen.findByText('后端炸了');
    expect(screen.getByText('这一轮没跑完')).toBeTruthy();
    // 问题还在（重试是**重跑这一轮** ✓，不是重发一遍问题 ✓）。
    expect(screen.getByText('hi')).toBeTruthy();

    const retry = screen.getByRole('button', { name: '重试这一轮' });
    fireEvent.click(retry);

    await waitFor(() => expect(streamCalls.count).toBe(2));
  });
});
