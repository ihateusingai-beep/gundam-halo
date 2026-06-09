/**
 * Live2D configuration context — holds the current ModelInfo
 * adapted from Open-LLM-VTuber for Gundam Halo
 * (no Electron/useConfig dependency)
 */
import { createContext, useContext, useState, useMemo } from "react";
import { ModelInfo } from "./live2d-types";

interface Live2DConfigState {
  modelInfo?: ModelInfo;
  setModelInfo: (info: ModelInfo | undefined) => void;
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;
}

const DEFAULT_MODEL_INFO: ModelInfo = {
  url: "",
  kScale: 0.5,
  initialXshift: 0,
  initialYshift: 0,
  emotionMap: {},
  scrollToResize: true,
};

export const Live2DConfigContext = createContext<Live2DConfigState | null>(null);

export function Live2DConfigProvider({ children }: { children: React.ReactNode }) {
  const [isLoading, setIsLoading] = useState(false);
  const [modelInfo, setModelInfoState] = useState<ModelInfo | undefined>(
    DEFAULT_MODEL_INFO
  );

  const setModelInfo = (info: ModelInfo | undefined) => {
    if (!info?.url) {
      setModelInfoState(undefined);
      return;
    }

    // kScale doubles: Open-LLM-VTuber sends 0.5, we want 1.0
    const finalScale = Number(info.kScale || 0.5) * 2;

    setModelInfoState({
      ...info,
      kScale: finalScale,
      pointerInteractive:
        "pointerInteractive" in info
          ? info.pointerInteractive
          : (modelInfo?.pointerInteractive ?? true),
      scrollToResize:
        "scrollToResize" in info
          ? info.scrollToResize
          : (modelInfo?.scrollToResize ?? true),
    });
  };

  const contextValue = useMemo(
    () => ({ modelInfo, setModelInfo, isLoading, setIsLoading }),
    [modelInfo, isLoading]
  );

  return (
    <Live2DConfigContext.Provider value={contextValue}>
      {children}
    </Live2DConfigContext.Provider>
  );
}

export function useLive2DConfig() {
  const context = useContext(Live2DConfigContext);
  if (!context) {
    throw new Error(
      "useLive2DConfig must be used within Live2DConfigProvider"
    );
  }
  return context;
}