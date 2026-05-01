/* Backtest store — zustand */
import { create } from 'zustand';
import type { BacktestResult, CatalogEntry, Strategy } from '../types/backtest';

interface BacktestState {
  results: BacktestResult[];
  activeResult: BacktestResult | null;
  strategies: Strategy[];
  catalog: CatalogEntry[];
  setResults: (v: BacktestResult[]) => void;
  setActiveResult: (v: BacktestResult | null) => void;
  setStrategies: (v: Strategy[]) => void;
  setCatalog: (v: CatalogEntry[]) => void;
  updateResult: (taskId: string, updates: Partial<BacktestResult>) => void;
}

export const useBacktestStore = create<BacktestState>((set) => ({
  results: [],
  activeResult: null,
  strategies: [],
  catalog: [],
  setResults: (v) => set({ results: v }),
  setActiveResult: (v) => set({ activeResult: v }),
  setStrategies: (v) => set({ strategies: v }),
  setCatalog: (v) => set({ catalog: v }),
  updateResult: (taskId, updates) => set((state) => ({
    results: state.results.map(r => r.task_id === taskId ? { ...r, ...updates } : r),
    activeResult: state.activeResult?.task_id === taskId
      ? { ...state.activeResult, ...updates }
      : state.activeResult,
  })),
}));
