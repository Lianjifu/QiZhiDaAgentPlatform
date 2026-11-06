/**
 * **一轮** ✓ —— 一个问题 + 一个回答 + 一行小结 ✓。
 *
 * ⚠️ **降级要说清楚** ✓（召回 / 压缩降级时回答是不完整的 ✓ —— 不说就是骗 ✓）。
 * ⚠️ **失败放这一轮里** ✓（不是飘在页面顶部的一行黄字 ✓ —— 那样不知道是
 * 哪一轮坏的 ✗✗）。
 */
import { memo, useEffect, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { MarkdownView } from '@/features/agents/components/MarkdownView';
import { AttachmentChip } from '../blocks/AttachmentChip';
import { ArtifactCard } from '../blocks/ArtifactCard';
import { MessageExtrasView } from '../blocks/MessageExtrasView';
import { PlanProposalCard } from '../blocks/PlanProposalCard';
import { FailureCard } from './FailureCard';
import { TurnMetaLine } from './TurnMetaLine';
import { degradedLabel, resolveTurnFacts, type ChatMessageView } from './turns';
import type { ApiTurn } from '../schema';

const TYPING_PHRASES = ['我在想呢…', '打字中…', '马上就好~', '让我看看…', '嗯,再琢磨一下', '等我一下'];

/**
 * 首字到达前的占位 —— deepseek first-token 1.5-7s ✓，
 * 没有这个提示用户会以为卡死 ✓。
 */
export function CopilotTypingIndicator() {
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => setIdx((i) => (i + 1) % TYPING_PHRASES.length), 1200);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <div
      data-testid="copilot-generating"
      className="flex items-center gap-2 text-[var(--text-muted)]"
      role="status"
      aria-live="polite"
    >
      <span className="inline-flex items-end gap-0.5" aria-hidden="true">
        <span
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--brand)]"
          style={{ animationDelay: '0ms', animationDuration: '900ms' }}
        />
        <span
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--brand)]"
          style={{ animationDelay: '150ms', animationDuration: '900ms' }}
        />
        <span
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--brand)]"
          style={{ animationDelay: '300ms', animationDuration: '900ms' }}
        />
      </span>
      <span key={idx} className="animate-[fadein_300ms_ease-out] text-sm tabular-nums">
        {TYPING_PHRASES[idx]}
        <span className="ml-0.5 inline-block w-3 animate-pulse">▍</span>
      </span>
    </div>
  );
}

export type TurnBlockProps = {
  turnKey: string;
  question?: ChatMessageView;
  answer?: ChatMessageView;
  /** 回答那条消息在消息数组里的下标 ✓ —— 重试要靠它复用原来的位置 ✓。 */
  answerIndex?: number;
  /** 后端那一轮的事实 ✓（重开会话时才有 ✓）。 */
  apiTurn?: ApiTurn;
  sessionId?: string;
  streaming?: boolean;
  feedback?: 5 | 1;
  onFeedback?: (turnKey: string, turnId: string | undefined, rating: 5 | 1) => void;
  onRetry?: (question: string, answerIndex: number) => void;
  retrying?: boolean;
};

/**
 * ⚠️ **记忆化** ✓ —— 流式时每个 chunk 都会重渲染整页 ✓ —— 历史那些轮次不该
 * 跟着重渲染 ✓（它们的内容一个字都没变 ✓）。
 *
 * ⚠️ **props 必须是稳定的引用** ✓ —— 消息对象在数组复制时**保持身份** ✓
 * （只有被改的那条换新对象 ✓）→ 浅比较就能挡住 ✓。
 */
export const TurnBlock = memo(function TurnBlock({
  turnKey,
  question,
  answer,
  answerIndex,
  apiTurn,
  sessionId,
  streaming,
  feedback,
  onFeedback,
  onRetry,
  retrying,
}: TurnBlockProps) {
  const facts = resolveTurnFacts(answer, apiTurn);
  const error = answer?.error;

  return (
    <section className="space-y-3" data-testid="turn-block">
      {question ? (
        <div className="flex justify-end">
          <div className="max-w-[86%] whitespace-pre-wrap rounded-2xl bg-[var(--text)] px-5 py-3 text-sm leading-6 text-[var(--surface-1)] shadow-sm">
            {question.content}
          </div>
        </div>
      ) : null}

      <article className="space-y-3 text-[15px] leading-7 text-[var(--text-secondary)]">
        {error ? (
          <FailureCard
            title={error.title ?? '这一轮没跑完'}
            message={error.message}
            code={error.code}
            onRetry={
              onRetry && question && answerIndex != null
                ? () => onRetry(question.content, answerIndex)
                : undefined
            }
            retrying={retrying}
          />
        ) : (
          <>
            {answer?.plan && sessionId ? (
              <PlanProposalCard proposal={answer.plan} sessionId={sessionId} />
            ) : null}
            {answer?.content ? (
              <MarkdownView source={answer.content} />
            ) : streaming ? (
              <CopilotTypingIndicator />
            ) : null}
            {answer?.artifacts && answer.artifacts.length > 0 ? (
              <div className="space-y-2">
                {answer.artifacts.map((artifact) => (
                  <ArtifactCard key={artifact.artifact_id} artifact={artifact} />
                ))}
              </div>
            ) : null}
            {answer?.attachments && answer.attachments.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {answer.attachments.map((attachment) => (
                  <AttachmentChip key={attachment.attachment_id} attachment={attachment} />
                ))}
              </div>
            ) : null}
            {facts.extras ? <MessageExtrasView extras={facts.extras} /> : null}
          </>
        )}

        {facts.degraded.length > 0 ? (
          <p className="flex items-start gap-1.5 rounded-lg border border-amber-200 bg-amber-50/70 px-3 py-2 text-[11px] leading-5 text-amber-900">
            <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-amber-600" aria-hidden="true" />
            <span>
              本轮降级：{degradedLabel(facts.degraded)} —— 回答可能不完整
            </span>
          </p>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <TurnMetaLine facts={facts} />
          {sessionId && onFeedback && !streaming && !error ? (
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => onFeedback(turnKey, apiTurn?.turnId ?? answer?.turnId, 5)}
                disabled={Boolean(feedback)}
                className="rounded-md px-1.5 py-0.5 text-[11px] text-[var(--text-muted)] hover:bg-[var(--bg-elevated)] disabled:opacity-60"
                aria-label="这条回答有帮助"
                title="有帮助"
              >
                👍{feedback === 5 ? ' 已反馈' : ''}
              </button>
              <button
                type="button"
                onClick={() => onFeedback(turnKey, apiTurn?.turnId ?? answer?.turnId, 1)}
                disabled={Boolean(feedback)}
                className="rounded-md px-1.5 py-0.5 text-[11px] text-[var(--text-muted)] hover:bg-[var(--bg-elevated)] disabled:opacity-60"
                aria-label="这条回答没帮助"
                title="没帮助"
              >
                👎{feedback === 1 ? ' 已反馈' : ''}
              </button>
            </div>
          ) : null}
        </div>
      </article>
    </section>
  );
});
