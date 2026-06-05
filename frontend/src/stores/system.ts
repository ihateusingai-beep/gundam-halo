import { create } from "zustand";
import { api } from "@/lib/api";
import type { Gauges } from "@/types/api";

interface SystemState {
  gauges: Gauges | null;
  loading: boolean;
  error: string | null;
  fetchGauges: () => Promise<void>;
  startPolling: () => () => void;
}

export const useSystemStore = create<SystemState>((set) => ({
  gauges: null,
  loading: false,
  error: null,

  fetchGauges: async () => {
    try {
      const gauges = await api.getGauges();
      set({ gauges, error: null });
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  startPolling: () => {
    const tick = () => {
      useSystemStore.getState().fetchGauges();
    };
    tick(); // immediate
    const id = setInterval(tick, 2000);
    return () => clearInterval(id);
  },
}));
