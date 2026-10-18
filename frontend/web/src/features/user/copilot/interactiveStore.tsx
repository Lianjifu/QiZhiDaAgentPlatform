/**
 * InteractiveStore — 前端交互动作的状态容器.
 *
 * 5 个 stub tool (ask_user_question / notify_user / plan_submit /
 * todo_write / delegate_to_agent) 在 backend 完成后, SSE 流会再发一个
 * `interactive_action` 事件. 这个 store 接收并分派:
 *
 *   - show_question_card → 当前 pending 的 question (modal)
 *   - toast              → toast 队列 (FIFO 自动消失)
 *   - render_plan        → 当前 pending 的 plan (sticky 条)
 *   - render_todo_list   → 累计的 todo 列表 (LWW)
 *   - delegate_agent     → 立即触发 router.push (前台组件无事可做)
 *
 * 用法:
 *   <InteractiveProvider value={store}>
 *     <InteractionHost />          // 监听 + 渲染
 *     <CopilotPage>...             // 用 store.onAnswer / store.onPlanDecision
 *   </InteractiveProvider>
 *
 * 或直接 useInteractive() 在组件里读 + dispatch.
 */
import { createContext, useContext, useState, type ReactNode } from 'react';

// ── 类型 ──────────────────────────────────────────────────────────────

export type InteractiveAction =
  | 'show_question_card'
  | 'toast'
  | 'render_plan'
  | 'render_todo_list'
  | 'delegate_agent';

export type PendingQuestion = {
  call_id: string;
  questions: QuestionSpec[];
  /** 用户提交答案时调用 — 由 CopilotPage 注入,负责 POST /answer */
  onResolve: (answers: AnswerPayload[]) => Promise<void> | void;
};

export type QuestionSpec = {
  question: string;
  header?: string;
  options: { label: string; description?: string }[];
  multi_select?: boolean;
};

export type AnswerPayload = {
  question_index: number;
  selected: string[]; // option.label 数组; 单选也用 [label]
};

export type PendingPlan = {
  call_id: string;
  plan_id: string;
  title: string;
  steps: { id: string; title: string; description?: string; status?: string }[];
  reason?: string;
  onResolve: (decision: 'approve' | 'reject', reason?: string) => Promise<void> | void;
};

export type ToastMsg = {
  id: string;
  title: string;
  body?: string;
  level: 'info' | 'warn' | 'error' | 'success';
  delivered_at: string;
  /** 自动消失毫秒 (override). 默认: info 4000 / warn 6000 / error 长显 */
  ttl_ms?: number;
};

export type TodoItem = {
  id: string;
  content: string;
  status: 'pending' | 'in_progress' | 'completed';
  active_form?: string;
};

// ── Store 接口 ─────────────────────────────────────────────────────────

export interface InteractiveStore {
  // 当前 pending (同时只一个 question / 一个 plan)
  question: PendingQuestion | null;
  plan: PendingPlan | null;

  // 队列 / 累计
  toasts: ToastMsg[];
  todos: TodoItem[];

  // ── dispatch (SSE consumer 调) ──
  handleAction: (
    call_id: string,
    action: InteractiveAction,
    payload: Record<string, unknown>,
    onResolve: (payload: Record<string, unknown>) => Promise<void> | void,
  ) => void;

  // ── 主动 dismiss ──
  dismissQuestion: () => void;
  dismissPlan: () => void;
  dismissToast: (id: string) => void;
}

// ── Context ────────────────────────────────────────────────────────────

const InteractiveCtx = createContext<InteractiveStore | null>(null);

export function InteractiveProvider({
  children,
}: {
  children: ReactNode;
}) {
  const [question, setQuestion] = useState<PendingQuestion | null>(null);
  const [plan, setPlan] = useState<PendingPlan | null>(null);
  const [toasts, setToasts] = useState<ToastMsg[]>([]);
  const [todos, setTodos] = useState<TodoItem[]>([]);

  const handleAction: InteractiveStore['handleAction'] = (
    call_id,
    action,
    payload,
    onResolve,
  ) => {
    if (action === 'show_question_card') {
      const questions = Array.isArray(payload.questions)
        ? (payload.questions as QuestionSpec[])
        : [];
      setQuestion({
        call_id,
        questions,
        onResolve: (answers) => {
          void onResolve({ answers });
          setQuestion(null);
        },
      });
    } else if (action === 'render_plan') {
      const steps = Array.isArray(payload.steps)
        ? (payload.steps as PendingPlan['steps'])
        : [];
      setPlan({
        call_id,
        plan_id: String(payload.plan_id ?? call_id),
        title: String(payload.title ?? '执行计划'),
        steps,
        reason: payload.reason as string | undefined,
        onResolve: (decision, reason) => {
          void onResolve({ plan_id: payload.plan_id, decision, reason });
          setPlan(null);
        },
      });
    } else if (action === 'toast') {
      const level = (payload.level ?? 'info') as ToastMsg['level'];
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const ttl =
        level === 'error'
          ? undefined // 长显
          : level === 'warn'
            ? 6000
            : level === 'success'
              ? 3000
              : 4000;
      setToasts((current) => [
        ...current,
        {
          id,
          title: String(payload.title ?? ''),
          body: (payload.body as string | undefined) ?? undefined,
          level,
          delivered_at:
            (payload.delivered_at as string | undefined) ?? new Date().toISOString(),
          ttl_ms: ttl,
        },
      ]);
      // 自动 dismiss (长显的没有 ttl, 不自动消失)
      if (ttl !== undefined) {
        window.setTimeout(() => {
          setToasts((current) => current.filter((t) => t.id !== id));
        }, ttl);
      }
    } else if (action === 'render_todo_list') {
      const list = Array.isArray(payload.todos)
        ? (payload.todos as TodoItem[])
        : [];
      setTodos(list);
    } else if (action === 'delegate_agent') {
      // 不在 store 里留状态 — frontend 拿到事件后立即 router.push
      void onResolve({
        agent_id: payload.agent_id,
        task: payload.task,
      });
    }
  };

  const dismissQuestion = () => setQuestion(null);
  const dismissPlan = () => setPlan(null);
  const dismissToast = (id: string) =>
    setToasts((current) => current.filter((t) => t.id !== id));

  return (
    <InteractiveCtx.Provider
      value={{
        question,
        plan,
        toasts,
        todos,
        handleAction,
        dismissQuestion,
        dismissPlan,
        dismissToast,
      }}
    >
      {children}
    </InteractiveCtx.Provider>
  );
}

export function useInteractive(): InteractiveStore {
  const v = useContext(InteractiveCtx);
  if (!v) {
    throw new Error(
      'useInteractive must be used inside <InteractiveProvider>',
    );
  }
  return v;
}

export const InteractiveContext = InteractiveCtx;