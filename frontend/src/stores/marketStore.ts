/* Market data store — zustand */
import { create } from 'zustand';
import type { ADSnapshot, PCRSnapshot, VIXSnapshot, CollectorStatus } from '../types/market';

interface MarketState {
  vwap: Record<string, Record<string, number>>;
  ad: ADSnapshot | null;
  pcr: PCRSnapshot | null;
  vix: VIXSnapshot | null;
  collectorStatus: CollectorStatus | null;
  lastUpdate: string | null;
  setVwap: (v: Record<string, Record<string, number>>) => void;
  setAd: (v: ADSnapshot) => void;
  setPcr: (v: PCRSnapshot) => void;
  setVix: (v: VIXSnapshot) => void;
  setCollectorStatus: (v: CollectorStatus) => void;
  updateFromSnapshot: (data: Record<string, unknown>) => void;
}

export const useMarketStore = create<MarketState>((set) => ({
  vwap: {},
  ad: null,
  pcr: null,
  vix: null,
  collectorStatus: null,
  lastUpdate: null,
  setVwap: (v) => set({ vwap: v }),
  setAd: (v) => set({ ad: v }),
  setPcr: (v) => set({ pcr: v }),
  setVix: (v) => set({ vix: v }),
  setCollectorStatus: (v) => set({ collectorStatus: v }),
  updateFromSnapshot: (data) => set((state) => {
    const asObj = (value: unknown): Record<string, unknown> =>
      value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
    const pickData = (value: unknown): Record<string, unknown> => {
      const root = asObj(value);
      const nested = asObj(root.data);
      return Object.keys(nested).length ? nested : root;
    };

    return {
      ...state,
      vwap: (pickData(data.vwap) as Record<string, Record<string, number>>) ?? state.vwap,
      ad: (pickData(data.ad) as unknown as ADSnapshot) ?? state.ad,
      pcr: (pickData(data.pcr) as unknown as PCRSnapshot) ?? state.pcr,
      vix: (pickData(data.vix) as unknown as VIXSnapshot) ?? state.vix,
      lastUpdate: new Date().toISOString(),
    };
  }),
}));
