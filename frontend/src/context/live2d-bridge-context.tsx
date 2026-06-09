/**
 * Live2D Bridge context — exposes voice WS state to React components.
 * Wraps the module-level singleton in halo-live2d-bridge.ts.
 */
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import {
  getLive2DState,
  subscribeToVoice,
  type Live2DState,
  type VoiceWSEvent,
} from "@/services/halo-live2d-bridge";

interface HaloLive2DContextValue {
  state: Live2DState;
  /** Manually trigger a Live2D expression + motion (for testing / tool calls). */
  trigger: (expression: string, motion: string) => void;
  /** Subscribe to voice WS events. Returns unsubscribe fn. */
  onVoiceEvent: (type: string | "*", handler: (e: VoiceWSEvent) => void) => () => void;
}

const HaloLive2DContext = createContext<HaloLive2DContextValue | null>(null);

export function HaloLive2DProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<Live2DState>(() => getLive2DState());

  useEffect(() => {
    const unsubscribe = subscribeToVoice("*", () => {
      // Re-fetch full state on any event
      setState(getLive2DState());
    });
    return unsubscribe;
  }, []);

  const value: HaloLive2DContextValue = {
    state,
    trigger: (expression: string, motion: string) => {
      // Dynamic import to avoid circular deps
      import("@/services/halo-live2d-bridge").then(
        ({ triggerLive2D }) => triggerLive2D(expression, motion)
      );
    },
    onVoiceEvent: (type, handler) => subscribeToVoice(type, handler),
  };

  return (
    <HaloLive2DContext.Provider value={value}>
      {children}
    </HaloLive2DContext.Provider>
  );
}

export function useHaloLive2D(): HaloLive2DContextValue {
  const ctx = useContext(HaloLive2DContext);
  if (!ctx) {
    throw new Error("useHaloLive2D must be used within HaloLive2DProvider");
  }
  return ctx;
}