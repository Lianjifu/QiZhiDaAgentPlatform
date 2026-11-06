import { describe, expect, it } from 'vitest';
import { buildTurns, degradedLabel, resolveTurnFacts } from './turns';
import type { ApiTurn } from '../schema';

function apiTurn(overrides: Partial<ApiTurn> = {}): ApiTurn {
  return {
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
    extras: {},
    ...overrides,
  };
}

describe('对话轮次', () => {
  it('一问一答归成一轮', () => {
    const turns = buildTurns([
      { role: 'user', content: '问题一', turnId: 'turn-1' },
      { role: 'assistant', content: '回答一', turnId: 'turn-1' },
      { role: 'user', content: '问题二', turnId: 'turn-2' },
      { role: 'assistant', content: '回答二', turnId: 'turn-2' },
    ]);
    expect(turns).toHaveLength(2);
    expect(turns[0].question?.content).toBe('问题一');
    expect(turns[0].answer?.content).toBe('回答一');
    expect(turns[1].answer?.content).toBe('回答二');
    expect(turns[0].answerIndex).toBe(1);
  });

  it('审批恢复开了新一轮 —— 不并成一块', () => {
    const turns = buildTurns([
      { role: 'user', content: '问题', turnId: 'turn-1' },
      { role: 'assistant', content: '第一轮的回答', turnId: 'turn-1' },
      { role: 'assistant', content: '恢复后的回答', turnId: 'turn-2' },
    ]);
    expect(turns).toHaveLength(2);
    expect(turns[1].answer?.content).toBe('恢复后的回答');
  });

  it('后端那份事实优先 —— 流式累积的只补空', () => {
    const turn = buildTurns([
      { role: 'user', content: '问题', turnId: 'turn-1' },
      { role: 'assistant', content: '回答', turnId: 'turn-1', usage: { inputTokens: 1, outputTokens: 2 } },
    ])[0];
    const facts = resolveTurnFacts(turn.answer, apiTurn());
    expect(facts.durationMs).toBe(3174);
    expect(facts.inputTokens).toBe(2228);
    expect(facts.outputTokens).toBe(122);
    expect(facts.costUsd).toBe(0.0001);
    expect(facts.modelVersion).toBe('deepseek-flash');
  });

  it('没有后端事实时用流式累积的', () => {
    const turn = buildTurns([
      { role: 'user', content: '问题' },
      { role: 'assistant', content: '回答', usage: { inputTokens: 7, outputTokens: 9 } },
    ])[0];
    const facts = resolveTurnFacts(turn.answer);
    expect(facts.inputTokens).toBe(7);
    expect(facts.outputTokens).toBe(9);
  });

  it('工具数与知识命中数从 extras 数出来', () => {
    const turn = buildTurns([
      { role: 'user', content: '问题', turnId: 'turn-1' },
      { role: 'assistant', content: '回答', turnId: 'turn-1' },
    ])[0];
    const facts = resolveTurnFacts(
      turn.answer,
      apiTurn({
        extras: {
          toolCalls: [
            { id: 'c1', tool_name: 'shell', status: 'succeeded' },
            { id: 'c2', tool_name: 'search', status: 'succeeded' },
          ],
          knowledgeHits: {
            query: '考勤',
            hits: [{ id: 'k1', title: '考勤与假期规定', snippet: '', score: 0.9 }],
          },
        },
      }),
    );
    expect(facts.toolCount).toBe(2);
    expect(facts.knowledgeCount).toBe(1);
  });

  it('降级标记认得出就翻译, 认不出就原样显示', () => {
    expect(degradedLabel(['recall_degraded'])).toBe('知识召回降级');
    expect(degradedLabel(['recall_degraded', 'weird_flag'])).toBe('知识召回降级、weird_flag');
  });
});
