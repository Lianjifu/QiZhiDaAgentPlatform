/**
 * FlowEditor — 工作流编辑器(三栏布局:节点类型 + ReactFlow 画布 + 属性面板)。
 *
 * readOnly 模式(查看):
 * - 左侧节点类型 disabled + opacity 降低
 * - React Flow 不可拖/不可连/不可选
 * - 右侧属性面板输入 disabled + 隐藏「高级配置 / 删除节点」
 *
 * 顶部 toolbar 仅保留:返回 + 名称 + 状态徽标
 * 「保存 / 版本 / 发布 / 编辑 toggle / 删除」 等动作上移到 WorkflowDetailPage 的页面级 header,
 * 保持 FlowEditor 只关心画布本身。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import ReactFlow, {
  Background as RFBackground,
  Controls as RFControls,
  MiniMap,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { ChevronDown, ChevronRight, Plug, Play, GitBranch, Brain, CheckCircle2, Plus, X } from 'lucide-react';
import type { Flow, FlowNodeData, NodeKind, NodeTypeChild, Tone, VarField } from '../schema';
import { NODE_KIND_LABEL, NODE_TYPE_TREE, STATUS_BADGE, nodeKindIcon, uid } from './constants';
import { NODE_TYPES } from './FlowNodeView';

const KIND_TONE: Record<NodeKind, Tone> = {
  trigger: 'info',
  tool: 'success',
  agent: 'purple',
  condition: 'warn',
  end: 'danger',
};

function toneForKind(kind: NodeKind): { badge: string } {
  const t = KIND_TONE[kind];
  const map: Record<Tone, string> = {
    brand: 'bg-[var(--brand-soft)] text-[var(--brand)]',
    info: 'bg-blue-50 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300',
    success: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300',
    warn: 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300',
    danger: 'bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300',
    purple: 'bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300',
  };
  return { badge: map[t] };
}

interface FlowEditorProps {
  flow: Flow;
  selectedNodeId: string | null;
  setSelectedNodeId: (id: string | null) => void;
  setFlows: React.Dispatch<React.SetStateAction<Flow[]>>;
  onOpenNodeConfig: (n: Node<FlowNodeData>) => void;
  setNotice: (s: string) => void;
  onChange?: (nodes: Node<FlowNodeData>[], edges: Edge[]) => void;
  readOnly?: boolean;
}

const KIND_ICON: Record<NodeKind, typeof Play> = {
  trigger: Play,
  tool: Plug,
  agent: Brain,
  condition: GitBranch,
  end: CheckCircle2,
};

export function FlowEditor({ flow, selectedNodeId, setSelectedNodeId, setFlows, onChange, onOpenNodeConfig, setNotice, readOnly = false }: FlowEditorProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState(flow.initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(flow.initialEdges);
  const [openGroups, setOpenGroups] = useState<Record<NodeKind, boolean>>({
    trigger: true, tool: true, agent: true, condition: false, end: false,
  });

  useEffect(() => {
    setNodes(flow.initialNodes);
    setEdges(flow.initialEdges);
  }, [flow.id, setEdges, setNodes]);

  useEffect(() => {
    if (!readOnly) onChange?.(nodes, edges);
  }, [edges, nodes, onChange, readOnly]);

  const onConnect = useCallback((connection: Connection) => {
    setEdges((eds) => addEdge({ ...connection, type: 'smoothstep', animated: true }, eds));
  }, [setEdges]);

  const selectedNode = useMemo(() => nodes.find((n) => n.id === selectedNodeId) || null, [nodes, selectedNodeId]);

  const updateNodeData = (patch: Partial<FlowNodeData>) => {
    setNodes((nds) => nds.map((n) => n.id === selectedNodeId ? { ...n, data: { ...n.data, ...patch } } : n));
  };

  const updateNodeConfig = (key: string, value: string) => {
    setNodes((nds) => nds.map((n) => n.id === selectedNodeId ? {
      ...n, data: { ...n.data, config: { ...n.data.config, [key]: value } },
    } : n));
  };

  const updateVar = (which: 'inputs' | 'outputs', idx: number, next: VarField) => {
    setNodes((nds) => nds.map((n) => {
      if (n.id !== selectedNodeId) return n;
      const list = [...(n.data[which] ?? [])];
      list[idx] = next;
      return { ...n, data: { ...n.data, [which]: list } };
    }));
  };

  const addVar = (which: 'inputs' | 'outputs') => {
    setNodes((nds) => nds.map((n) => {
      if (n.id !== selectedNodeId) return n;
      const list = [...(n.data[which] ?? []), { name: 'new_var', type: 'string' as const }];
      return { ...n, data: { ...n.data, [which]: list } };
    }));
  };

  const removeVar = (which: 'inputs' | 'outputs', idx: number) => {
    setNodes((nds) => nds.map((n) => {
      if (n.id !== selectedNodeId) return n;
      const list = [...(n.data[which] ?? [])];
      list.splice(idx, 1);
      return { ...n, data: { ...n.data, [which]: list } };
    }));
  };

  const deleteSelectedNode = () => {
    if (!selectedNodeId) return;
    setNodes((nds) => nds.filter((n) => n.id !== selectedNodeId));
    setEdges((eds) => eds.filter((e) => e.source !== selectedNodeId && e.target !== selectedNodeId));
    setSelectedNodeId(null);
    setNotice('已删除选中节点及关联连线。');
  };

  const addChildToCanvas = (kind: NodeKind, child: NodeTypeChild) => {
    if (readOnly) return;
    const group = NODE_TYPE_TREE.find((g) => g.kind === kind);
    if (!group) return;
    const id = uid('n');
    const node: Node<FlowNodeData> = {
      id, type: 'flowNode',
      position: { x: 240 + Math.random() * 80, y: 80 + Math.random() * 80 },
      data: {
        label: child.label,
        subtitle: child.subtitle,
        kind,
        config: { ...(child.defaults ?? group.children[0]?.defaults ?? {}) },
        inputs: child.inputs,
        outputs: child.outputs,
      },
    };
    setNodes((nds) => [...nds, node]);
    setSelectedNodeId(id);
    setNotice(`已加入「${child.label}」,可在画布上调整位置。`);
  };

  return (
    <div className="flex h-[calc(100vh-7rem)] min-h-[640px] flex-col gap-3">
      <section className="grid min-h-0 flex-1 gap-3 xl:grid-cols-[280px_minmax(0,1fr)_280px]">
        <aside className={`flex min-h-0 flex-col rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-4 ${readOnly ? 'pointer-events-none opacity-80' : ''}`}>
          <div className="flex items-start gap-2">
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-[var(--brand-soft)] text-[var(--brand)]">
              {(() => { const Icon = nodeKindIcon(flow.initialNodes[0]?.data.kind ?? 'trigger'); return <Icon className="h-4 w-4" />; })()}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold leading-tight">{flow.name}</p>
              <div className="mt-1 flex flex-wrap items-center gap-1">
                <span className={`inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[9px] font-semibold ${STATUS_BADGE[flow.status].className}`}>
                  <span className={`h-1 w-1 rounded-full ${STATUS_BADGE[flow.status].dot}`} />
                  {STATUS_BADGE[flow.status].label}
                </span>
                <span className="rounded-md bg-[var(--bg-elevated)] px-1.5 py-0.5 text-[9px] font-mono text-[var(--text-muted)]">{flow.trigger}</span>
              </div>
            </div>
          </div>

          <div className="mt-4 flex items-center justify-between border-b border-[var(--border)] pb-2">
            <p className="text-[11px] font-semibold text-[var(--text-secondary)]">节点类型</p>
            <p className="text-[10px] text-[var(--text-muted)]">{readOnly ? '只读' : '点击加入'}</p>
          </div>

          <div className="mt-2 flex-1 space-y-2 overflow-y-auto pr-1">
            {NODE_TYPE_TREE.map((group) => {
              const open = openGroups[group.kind];
              const Icon = KIND_ICON[group.kind];
              return (
                <div key={group.kind} className="rounded-lg border border-[var(--border)] bg-[var(--bg-app)]">
                  <button
                    type="button"
                    onClick={() => setOpenGroups((prev) => ({ ...prev, [group.kind]: !prev[group.kind] }))}
                    disabled={readOnly}
                    className="flex w-full items-center gap-1.5 rounded-lg px-2.5 py-2 text-left text-xs font-semibold hover:bg-[var(--bg-hover)] disabled:cursor-not-allowed"
                  >
                    {open ? <ChevronDown className="h-3 w-3 text-[var(--text-muted)]" /> : <ChevronRight className="h-3 w-3 text-[var(--text-muted)]" />}
                    <Icon className="h-3.5 w-3.5 text-[var(--brand)]" />
                    <span className="flex-1">{group.label}</span>
                    <span className="text-[9px] text-[var(--text-muted)]">{group.children.length}</span>
                  </button>
                  {open && (
                    <ul className="space-y-1 px-1.5 pb-2">
                      {group.children.map((child) => (
                        <li key={child.id}>
                          <button
                            type="button"
                            draggable={!readOnly}
                            onDragStart={(e) => e.dataTransfer.setData('application/reactflow', JSON.stringify({ kind: group.kind, child }))}
                            onClick={() => addChildToCanvas(group.kind, child)}
                            disabled={readOnly}
                            className="flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left hover:bg-[var(--surface-1)] disabled:cursor-not-allowed"
                          >
                            <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded bg-[var(--bg-elevated)] text-[var(--text-muted)]">
                              <Icon className="h-3 w-3" />
                            </span>
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-[11px] font-semibold leading-tight">{child.label}</p>
                              <p className="mt-0.5 truncate text-[10px] text-[var(--text-muted)]">{child.subtitle}</p>
                            </div>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          </div>
        </aside>

        <div className="min-h-0 overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodesDraggable={!readOnly}
            nodesConnectable={!readOnly}
            elementsSelectable={!readOnly}
            onNodesChange={(changes) => {
              onNodesChange(changes);
              const sel = changes.find((c) => c.type === 'select');
              if (sel && 'id' in sel && sel.id) setSelectedNodeId(sel.selected ? sel.id : null);
            }}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            nodeTypes={NODE_TYPES}
            onDrop={(e) => {
              if (readOnly) return;
              const raw = e.dataTransfer.getData('application/reactflow');
              if (!raw) return;
              let payload: { kind: NodeKind; child: NodeTypeChild } | null = null;
              try { payload = JSON.parse(raw); } catch { return; }
              if (!payload) return;
              const group = NODE_TYPE_TREE.find((g) => g.kind === payload.kind);
              if (!group) return;
              const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
              const id = uid('n');
              const node: Node<FlowNodeData> = {
                id, type: 'flowNode',
                position: { x: e.clientX - rect.left - 90, y: e.clientY - rect.top - 30 },
                data: {
                  label: payload.child.label,
                  subtitle: payload.child.subtitle,
                  kind: payload.kind,
                  config: { ...(payload.child.defaults ?? group.children[0]?.defaults ?? {}) },
                  inputs: payload.child.inputs,
                  outputs: payload.child.outputs,
                },
              };
              setNodes((nds) => [...nds, node]);
            }}
            onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; }}
            fitView
            fitViewOptions={{ padding: 0.2, maxZoom: 1.2 }}
            minZoom={0.3}
            maxZoom={1.5}
            proOptions={{ hideAttribution: true }}
          >
            <RFBackground gap={20} size={1} color="var(--border)" />
            <RFControls position="bottom-right" className="!bg-[var(--surface-1)] !border !border-[var(--border)] [&_button]:!bg-[var(--surface-1)] [&_button]:!border-[var(--border)] [&_button]:!text-[var(--text-secondary)] [&_button:hover]:!bg-[var(--bg-hover)]" />
            <MiniMap
              position="bottom-left"
              pannable
              zoomable
              nodeColor={() => 'var(--brand)'}
              maskColor="rgba(0,0,0,0.55)"
              style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}
            />
          </ReactFlow>
        </div>

        <aside className={`flex min-h-0 flex-col rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-4 ${readOnly && !selectedNode ? 'opacity-80' : ''}`}>
          <p className="text-xs font-semibold text-[var(--text-muted)]">{readOnly ? '节点信息' : '属性面板'}</p>
          {selectedNode ? (
            <div className="mt-3 flex-1 space-y-3 overflow-y-auto">
              {/* 基本信息 */}
              <section className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] p-3">
                <div className="flex items-center justify-between">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">基本信息</p>
                  <span className={`inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[9px] font-semibold ${toneForKind(selectedNode.data.kind).badge}`}>
                    {NODE_KIND_LABEL[selectedNode.data.kind]}
                  </span>
                </div>
                <div className="mt-2 space-y-2">
                  <label className="block">
                    <span className="text-[10px] text-[var(--text-muted)]">节点名称</span>
                    <input value={selectedNode.data.label} disabled={readOnly} onChange={(e) => updateNodeData({ label: e.target.value })} className="mt-1 h-8 w-full rounded-md border border-[var(--border)] bg-[var(--surface-1)] px-2 text-xs outline-none focus:border-[var(--brand)] disabled:cursor-not-allowed disabled:opacity-70" />
                  </label>
                  <label className="block">
                    <span className="text-[10px] text-[var(--text-muted)]">副标题</span>
                    <input value={selectedNode.data.subtitle} disabled={readOnly} onChange={(e) => updateNodeData({ subtitle: e.target.value })} className="mt-1 h-8 w-full rounded-md border border-[var(--border)] bg-[var(--surface-1)] px-2 text-xs outline-none focus:border-[var(--brand)] disabled:cursor-not-allowed disabled:opacity-70" />
                  </label>
                </div>
              </section>

              {/* 输入变量 */}
              <section className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] p-3">
                <div className="flex items-center justify-between">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">输入变量</p>
                  {!readOnly && (
                    <button type="button" onClick={() => addVar('inputs')} className="inline-flex items-center gap-0.5 rounded px-1 py-0.5 text-[10px] font-semibold text-[var(--brand)] hover:bg-[var(--surface-1)]">
                      <Plus className="h-2.5 w-2.5" />添加
                    </button>
                  )}
                </div>
                <ul className="mt-2 space-y-1.5">
                  {(selectedNode.data.inputs ?? []).length === 0 && (
                    <li className="text-[10px] italic text-[var(--text-muted)]">无输入(开始节点除外)</li>
                  )}
                  {(selectedNode.data.inputs ?? []).map((v, idx) => (
                    <li key={`in-${idx}-${v.name}`} className="flex items-center gap-1">
                      <input value={v.name} disabled={readOnly} onChange={(e) => updateVar('inputs', idx, { ...v, name: e.target.value })} className="h-7 min-w-0 flex-1 rounded border border-[var(--border)] bg-[var(--surface-1)] px-1.5 font-mono text-[11px] outline-none focus:border-[var(--brand)] disabled:cursor-not-allowed disabled:opacity-70" />
                      <select value={v.type} disabled={readOnly} onChange={(e) => updateVar('inputs', idx, { ...v, type: e.target.value as VarField['type'] })} className="h-7 rounded border border-[var(--border)] bg-[var(--surface-1)] px-1 text-[10px] uppercase outline-none focus:border-[var(--brand)] disabled:cursor-not-allowed disabled:opacity-70">
                        {(['string','number','boolean','object','array','file'] as const).map((t) => <option key={t} value={t}>{t}</option>)}
                      </select>
                      <button type="button" disabled={readOnly} onClick={() => updateVar('inputs', idx, { ...v, required: !v.required })} title="必填" className={`grid h-7 w-7 place-items-center rounded border text-[10px] font-bold ${v.required ? 'border-rose-300 bg-rose-50 text-rose-600 dark:bg-rose-500/15' : 'border-[var(--border)] bg-[var(--surface-1)] text-[var(--text-muted)]'} disabled:cursor-not-allowed disabled:opacity-70`}>
                        *
                      </button>
                      {!readOnly && (
                        <button type="button" onClick={() => removeVar('inputs', idx)} aria-label="删除变量" className="grid h-7 w-7 place-items-center rounded text-[var(--text-muted)] hover:bg-rose-50 hover:text-rose-500 dark:hover:bg-rose-500/15">
                          <X className="h-3 w-3" />
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              </section>

              {/* 输出变量 */}
              <section className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] p-3">
                <div className="flex items-center justify-between">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">输出变量</p>
                  {!readOnly && (
                    <button type="button" onClick={() => addVar('outputs')} className="inline-flex items-center gap-0.5 rounded px-1 py-0.5 text-[10px] font-semibold text-[var(--brand)] hover:bg-[var(--surface-1)]">
                      <Plus className="h-2.5 w-2.5" />添加
                    </button>
                  )}
                </div>
                <ul className="mt-2 space-y-1.5">
                  {(selectedNode.data.outputs ?? []).length === 0 && (
                    <li className="text-[10px] italic text-[var(--text-muted)]">无输出(结束节点除外)</li>
                  )}
                  {(selectedNode.data.outputs ?? []).map((v, idx) => (
                    <li key={`out-${idx}-${v.name}`} className="flex items-center gap-1">
                      <input value={v.name} disabled={readOnly} onChange={(e) => updateVar('outputs', idx, { ...v, name: e.target.value })} className="h-7 min-w-0 flex-1 rounded border border-[var(--border)] bg-[var(--surface-1)] px-1.5 font-mono text-[11px] outline-none focus:border-[var(--brand)] disabled:cursor-not-allowed disabled:opacity-70" />
                      <select value={v.type} disabled={readOnly} onChange={(e) => updateVar('outputs', idx, { ...v, type: e.target.value as VarField['type'] })} className="h-7 rounded border border-[var(--border)] bg-[var(--surface-1)] px-1 text-[10px] uppercase outline-none focus:border-[var(--brand)] disabled:cursor-not-allowed disabled:opacity-70">
                        {(['string','number','boolean','object','array','file'] as const).map((t) => <option key={t} value={t}>{t}</option>)}
                      </select>
                      <button type="button" disabled={readOnly} onClick={() => updateVar('outputs', idx, { ...v, required: !v.required })} title="必填" className={`grid h-7 w-7 place-items-center rounded border text-[10px] font-bold ${v.required ? 'border-rose-300 bg-rose-50 text-rose-600 dark:bg-rose-500/15' : 'border-[var(--border)] bg-[var(--surface-1)] text-[var(--text-muted)]'} disabled:cursor-not-allowed disabled:opacity-70`}>
                        *
                      </button>
                      {!readOnly && (
                        <button type="button" onClick={() => removeVar('outputs', idx)} aria-label="删除变量" className="grid h-7 w-7 place-items-center rounded text-[var(--text-muted)] hover:bg-rose-50 hover:text-rose-500 dark:hover:bg-rose-500/15">
                          <X className="h-3 w-3" />
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              </section>

              {/* 配置 + 高级 */}
              <section className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] p-3">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">配置</p>
                <div className="mt-2 space-y-2">
                  {Object.entries(selectedNode.data.config).map(([k, v]) => (
                    <label key={k} className="block">
                      <span className="text-[10px] text-[var(--text-muted)]">{k}</span>
                      <input value={v} disabled={readOnly} onChange={(e) => updateNodeConfig(k, e.target.value)} className="mt-1 h-8 w-full rounded-md border border-[var(--border)] bg-[var(--surface-1)] px-2 text-xs outline-none focus:border-[var(--brand)] disabled:cursor-not-allowed disabled:opacity-70" />
                    </label>
                  ))}
                </div>
                {!readOnly && (
                  <button type="button" onClick={() => onOpenNodeConfig(selectedNode)} className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-[var(--border)] bg-[var(--surface-1)] px-2.5 py-1.5 text-[11px] font-semibold text-[var(--text-secondary)] hover:border-[var(--brand)] hover:text-[var(--brand)]">
                    高级配置
                  </button>
                )}
              </section>

              {!readOnly && (
                <button type="button" onClick={deleteSelectedNode} className="inline-flex w-full items-center justify-center gap-1.5 rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700 hover:bg-rose-100 dark:bg-rose-500/15 dark:text-rose-300">
                  删除节点
                </button>
              )}
            </div>
          ) : (
            <div className="mt-3 rounded-lg border border-dashed border-[var(--border-strong)] p-6 text-center">
              <p className="mt-2 text-xs font-semibold">未选中节点</p>
              <p className="mt-1 text-[10px] text-[var(--text-muted)]">{readOnly ? '查看模式下点选画布上的节点,可在右侧查看节点信息。' : '点选画布上的节点,在右侧编辑属性;从节点左侧 / 右侧圆点拖动可连线。'}</p>
            </div>
          )}
        </aside>
      </section>
    </div>
  );
}
