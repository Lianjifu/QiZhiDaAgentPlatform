import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import Copilot from './CopilotPage';

// jsdom 没有实现 scrollIntoView —— 页面滚动到底的 effect 会调用它.
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

/**
 * **重开的会话** —— 那些数字还在 ✓。
 *
 * ⚠️ 耗时 / token / 成本 / 工具 / 知识命中**一直躺在库里** ✓（``session_turns``
 * + ``session_events`` ✓）—— 以前**没人读** ✗✗ → 重开一个会话就全没了 ✗✗。
 */
vi.mock('./copilotApi', async () => {
  const actual = await vi.importActual<typeof import('./copilotApi')>('./copilotApi');
  return {
    ...actual,
    listCopilotSessions: vi.fn(async () => [
      {
        id: 'sid-1',
        title: '考勤怎么算',
        preview: '标准工作时间 9:30-18:30',
        updatedAt: new Date().toISOString(),
        agentId: 'agent-1',
        agentName: '办公助手',
        model: 'deepseek-flash',
        turnCount: 1,
        lastStatus: 'succeeded',
        waitStatus: 'idle',
      },
    ]),
    loadCopilotSession: vi.fn(async () => ({
      id: 'sid-1',
      title: '考勤怎么算',
      preview: '标准工作时间 9:30-18:30',
      updatedAt: new Date().toISOString(),
      agentId: 'agent-1',
      agentName: '办公助手',
      model: 'deepseek-flash',
      messages: [
        { role: 'user', content: '考勤怎么算', turnId: 'turn-1' },
        { role: 'assistant', content: '标准工作时间 9:30-18:30', turnId: 'turn-1' },
      ],
      turns: [
        {
          turnId: 'turn-1',
          status: 'succeeded',
          startedAt: '2026-11-06T12:04:23.324081Z',
          finishedAt: '2026-11-06T12:04:26.498470Z',
          durationMs: 3174,
          modelVersion: 'deepseek-flash',
          agentVersion: 'v1',
          errorCode: null,
          inputTokens: 2228,
          outputTokens: 122,
          costUsd: 0.0001,
          degraded: [],
          extras: {
            knowledgeHits: {
              query: '考勤',
              hits: [{ id: 'k1', title: '考勤与假期规定', snippet: '午休 12:00-13:30', score: 0.9 }],
            },
          },
        },
      ],
    })),
    createCopilotSession: vi.fn(async () => ({ id: 'sid-1', messages: [] })),
    streamCopilotTurn: vi.fn(async () => {}),
  };
});

describe('Copilot 重开的会话', () => {
  afterEach(() => cleanup());

  it('每一轮的小结还在 —— 耗时 / token / 知识命中', async () => {
    render(
      <MemoryRouter>
        <Copilot />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByText('考勤怎么算'));

    await screen.findByText(/标准工作时间/);
    const meta = screen.getByTestId('turn-meta');
    expect(meta.textContent).toContain('耗时 3.2s');
    expect(meta.textContent).toContain('输入 2,228');
    expect(meta.textContent).toContain('输出 122');
    expect(meta.textContent).toContain('知识 1 条');
    // ⚠️ **知识命中的标题也还在** ✓（以前重开就没了 ✗✗）。
    expect(screen.getByText('考勤与假期规定')).toBeTruthy();
    // ⚠️ **头部显示的是真的智能体名** ✓（不是编的 ✓）。
    expect(screen.getByText('办公助手')).toBeTruthy();
  });
});
