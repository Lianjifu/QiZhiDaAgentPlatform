/**
 * 当前工作区状态 — 多工作区切换
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Workspace } from '@qzdap/web-types';

interface WorkspaceState {
  current: Workspace | null;
  currentWorkspaceId: string | null;
  list: Workspace[];
  setCurrent: (w: Workspace | null) => void;
  setCurrentId: (id: string | null) => void;
  setList: (list: Workspace[]) => void;
}

const STORAGE_KEY = 'qzdap:workspace';

export const useWorkspaceStore = create<WorkspaceState>()(
  persist(
    (set) => ({
      current: null,
      list: [],
      currentWorkspaceId: null,
      setCurrent: (w) => set({ current: w, currentWorkspaceId: w?.id ?? null }),
      setCurrentId: (id) => set({ currentWorkspaceId: id }),
      setList: (list) => set({ list }),
    }),
    {
      name: STORAGE_KEY,
      // 只持久化 workspaceId (current/lid 包含对象 + 列表, 大且会过期, 重新从 user 拿)
      partialize: (state) => ({ currentWorkspaceId: state.currentWorkspaceId }),
    },
  ),
);
