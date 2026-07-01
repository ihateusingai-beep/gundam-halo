/**
 * Live2D Bridge context — exposes voice WS state to React components.
 * Wraps the module-level singleton in halo-live2d-bridge.ts.
 *
 * Sprint 53 reduced the context surface: the `trigger` method
 * (which invoked the now-removed `triggerLive2D` from the bridge)
 * is gone. Callers only need `state` (lastEmotion / lastTrigger
 * for AvatarCard) — the bridge still subscribes to /ws/voice +
 * /ws so `lastEmotion` updates automatically.
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