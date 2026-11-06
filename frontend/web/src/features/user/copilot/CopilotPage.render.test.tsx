import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import Copilot from './CopilotPage';

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

/**
 * **流式时别把历史重渲染一遍** ✓。
 *
 * ⚠️ **markdown 解析是热路径** ✓ —— 一段回答 0.9ms ✓ —— 流式时每个 chunk 都
 * 触发一次整页重渲染 ✓ —— 之前**整段历史被重新 parse 一遍** ✓（轮次越多越
 * 平方级 ✗✗）。
 *
 * 这里把 MarkdownView 换成**计数的替身** ✓ —— 数字涨了就是回归了 ✗✗
 * （替身**故意不记忆化** ✓ —— 数的是**轮次块**重渲染了几次 ✓）。
 */
const mdRenders = vi.hoisted(() => [] as string[]);

vi.mock('@/features/agents/components/MarkdownView', async () => {
  const React = await import('react');
  return {
    MarkdownView: function MockMarkdownView({ source }: { source: string }) {
      mdRenders.push(source);
      return React.createElement('div', null, source);
    },
  };
});

vi.mock('./copilotApi', async () => {
  const actual = await vi.importActual<typeof import('./copilotApi')>('./copilotApi');
  return {
    ...actual,
    listCopilotSessions: vi.fn(async () => [
      { id: 'sid-1', title: '旧会话', preview: '', updatedAt: new Date().toISOString() },
    ]),
    createCopilotSession: vi.fn(async () => ({ id: 'sid-1', messages: [] })),
    loadCopilotSession: vi.fn(async () => ({
      id: 'sid-1',
      title: '旧会话',
      preview: '',
      updatedAt: new Date().toISOString(),
      messages: [
        { role: 'user', content: '旧问题', turnId: 'turn-1' },
        { role: 'assistant', content: '旧回答', turnId: 'turn-1' },
      ],
      turns: [],
    })),
    streamCopilotTurn: vi.fn(
      async (
        _sessionId: string,
        _content: string,
        onEvent: (event: string, data: Record<string, unknown>) => void,
      ) => {
        onEvent('message', { content: '新' });
        onEvent('message', { content: '回答' });
        onEvent('message', { content: '内容' });
        onEvent('done', { final_message: '新回答内容' });
      },
    ),
  };
});

describe('Copilot 流式渲染', () => {
  afterEach(() => {
    cleanup();
    mdRenders.length = 0;
  });

  it('历史那一轮不会跟着新 chunk 重渲染', async () => {
    render(
      <MemoryRouter
        initialEntries={[{ pathname: '/copilot', state: { agentId: 'agent-1', agentName: 'A' } }]}
      >
        <Copilot />
      </MemoryRouter>,
    );

    // 打开历史会话
    fireEvent.click(await screen.findByText('旧会话'));
    await screen.findByText('旧回答');
    expect(mdRenders.filter((text) => text === '旧回答').length).toBe(1);

    // 发一条新消息 —— 一串 chunk
    const input = screen.getByPlaceholderText('描述你想完成的工作...') as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: '新问题' } });
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }));

    await waitFor(() => expect(screen.getByText('新回答内容')).toBeTruthy());
    // ⚠️ **历史那轮只渲染过一次** ✓ —— 没跟着新 chunk 重来 ✓。
    expect(mdRenders.filter((text) => text === '旧回答').length).toBe(1);
  });

  it('MarkdownView 本身是记忆化的 —— 源码没变就别重新 parse', async () => {
    const actual = await vi.importActual<typeof import('@/features/agents/components/MarkdownView')>(
      '@/features/agents/components/MarkdownView',
    );
    const type = actual.MarkdownView as unknown as { $$typeof?: symbol };
    expect(type.$$typeof).toBe(Symbol.for('react.memo'));
  });
});
