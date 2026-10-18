/**
 * InteractionHost — 汇总所有 interactive-action UI.
 *
 * 用法: 直接挂在 CopilotPage 内部 (被 <InteractiveProvider> 包着):
 *   <InteractionHost />
 *
 * 它只读 store 然后挂 4 个 UI: question modal / plan 条 / todo 抽屉 / toast.
 * delegate_agent 不需要 UI 组件 — 由 streamCopilotTurn 回调里直接 router.push.
 */
import { InteractiveQuestionCard } from './blocks/InteractiveQuestionCard';
import { InteractiveToastHost } from './blocks/InteractiveToastHost';
import { InteractivePlanCard } from './blocks/InteractivePlanCard';
import { InteractiveTodoList } from './blocks/InteractiveTodoList';
import { useInteractive } from './interactiveStore';

export function InteractionHost() {
  const { question, plan, toasts, todos, dismissQuestion, dismissPlan, dismissToast } =
    useInteractive();

  return (
    <>
      {question && (
        <InteractiveQuestionCard
          pending={question}
          onDismiss={dismissQuestion}
        />
      )}
      {plan && <InteractivePlanCard pending={plan} onResolve={plan.onResolve} />}
      <InteractiveTodoList todos={todos} />
      <InteractiveToastHost toasts={toasts} onDismiss={dismissToast} />
    </>
  );
}