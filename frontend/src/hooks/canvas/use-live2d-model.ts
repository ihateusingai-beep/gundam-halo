/**
 * Live2D model loading + interaction hook
 * adapted from Open-LLM-VTuber for Gundam Halo
 * (stripped Electron IPC, pet mode, context menu)
 *
 * WebSDK is loaded via <script> tags before React mounts. We access it
 * via window globals instead of import statements so Vite doesn't try
 * to bundle the library code.
 */
// @ts-nocheck
/* eslint-disable no-underscore-dangle */
/* eslint-disable @typescript-eslint/ban-ts-comment */
/* eslint-disable no-use-before-define */
/* eslint-disable no-param-reassign */
/* eslint-disable @typescript-eslint/no-unused-vars */
import { useEffect, useRef, useCallback, useState } from "react";
import { ModelInfo } from "@/context/live2d-types";

// Access WebSDK via window globals (loaded via <script> in main.tsx)
// We don't import these directly — that would make Vite try to bundle them.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const getLAppDelegate = () => (window as any).LAppDelegate;
const getLAppLive2DManager = () => (window as any).LAppLive2DManager;
const getInitializeLive2D = () => (window as any).initializeLive2D;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const getLAppDefine = () => (window as any).LAppDefine;

interface UseLive2DModelProps {
  modelInfo: ModelInfo | undefined;
  canvasRef: React.RefObject<HTMLCanvasElement | null>;
}

interface Position {
  x: number;
  y: number;
}

const TAP_DURATION_THRESHOLD_MS = 200;
const DRAG_DISTANCE_THRESHOLD_PX = 5;

function parseModelUrl(url: string): {
  baseUrl: string;
  modelDir: string;
  modelFileName: string;
} {
  try {
    const urlObj = new URL(url);
    const { pathname } = urlObj;
    const lastSlashIndex = pathname.lastIndexOf("/");
    if (lastSlashIndex === -1) throw new Error("Invalid model URL format");

    const fullFileName = pathname.substring(lastSlashIndex + 1);
    const modelFileName = fullFileName.replace(".model3.json", "");

    const secondLastSlashIndex = pathname.lastIndexOf("/", lastSlashIndex - 1);
    if (secondLastSlashIndex === -1)
      throw new Error("Invalid model URL format");

    const modelDir = pathname.substring(
      secondLastSlashIndex + 1,
      lastSlashIndex
    );
    const baseUrl = `${urlObj.protocol}//${urlObj.host}${pathname.substring(
      0,
      secondLastSlashIndex + 1
    )}`;

    return { baseUrl, modelDir, modelFileName };
  } catch (error) {
    console.error("Error parsing model URL:", error);
    return { baseUrl: "", modelDir: "", modelFileName: "" };
  }
}

export const useLive2DModel = ({
  modelInfo,
  canvasRef,
}: UseLive2DModelProps) => {
  const [isDragging, setIsDragging] = useState(false);
  const [position, setPosition] = useState<Position>({ x: 0, y: 0 });
  const dragStartPos = useRef<Position>({ x: 0, y: 0 });
  const modelStartPos = useRef<Position>({ x: 0, y: 0 });
  const modelPositionRef = useRef<Position>({ x: 0, y: 0 });
  const prevModelUrlRef = useRef<string | null>(null);
  const mouseDownTimeRef = useRef<number>(0);
  const mouseDownPosRef = useRef<Position>({ x: 0, y: 0 });
  const isPotentialTapRef = useRef<boolean>(false);

  // Load/reload model when URL changes
  useEffect(() => {
    const currentUrl = modelInfo?.url;
    const LAppDefine = getLAppDefine();
    const sdkScale = LAppDefine?.CurrentKScale;
    const modelScale =
      modelInfo?.kScale !== undefined
        ? Number(modelInfo.kScale)
        : undefined;

    const needsUpdate =
      currentUrl &&
      (currentUrl !== prevModelUrlRef.current ||
        (sdkScale !== undefined &&
          modelScale !== undefined &&
          sdkScale !== modelScale));

    if (needsUpdate) {
      prevModelUrlRef.current = currentUrl;

      try {
        const { baseUrl, modelDir, modelFileName } = parseModelUrl(currentUrl);

        if (baseUrl && modelDir) {
          // Update LAppDefine via the global
          if (LAppDefine) {
            LAppDefine.ResourcesPath = baseUrl;
            LAppDefine.ModelDir = [modelDir];
            LAppDefine.ModelFileNames = [modelFileName];
            if (modelInfo.kScale !== undefined) {
              LAppDefine.CurrentKScale = Number(modelInfo.kScale);
            }
            LAppDefine.ModelDirSize = 1;
          }

          setTimeout(() => {
            const manager = getLAppLive2DManager();
            if (manager?.releaseInstance) manager.releaseInstance();
            const initFn = getInitializeLive2D();
            if (initFn) initFn();
          }, 500);
        }
      } catch (error) {
        console.error("Error processing model URL:", error);
      }
    }
  }, [modelInfo?.url, modelInfo?.kScale]);

  const getModelPosition = useCallback(() => {
    const adapter = (window as any).getLAppAdapter?.();
    if (adapter) {
      const model = adapter.getModel();
      if (model && model._modelMatrix) {
        const matrix = model._modelMatrix.getArray();
        return { x: matrix[12], y: matrix[13] };
      }
    }
    return { x: 0, y: 0 };
  }, []);

  const setModelPosition = useCallback((x: number, y: number) => {
    const adapter = (window as any).getLAppAdapter?.();
    if (adapter) {
      const model = adapter.getModel();
      if (model && model._modelMatrix) {
        const matrix = model._modelMatrix.getArray();
        const newMatrix = [...matrix];
        newMatrix[12] = x;
        newMatrix[13] = y;
        model._modelMatrix.setMatrix(newMatrix);
        modelPositionRef.current = { x, y };
      }
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      const currentPos = getModelPosition();
      modelPositionRef.current = currentPos;
      setPosition(currentPos);
    }, 500);
    return () => clearTimeout(timer);
  }, [modelInfo?.url, getModelPosition]);

  const getCanvasScale = useCallback(() => {
    const canvas = document.getElementById("canvas") as HTMLCanvasElement;
    if (!canvas) return { width: 1, height: 1, scale: 1 };
    const { width, height } = canvas;
    const scale = width / canvas.clientWidth;
    return { width, height, scale };
  }, []);

  const screenToModelPosition = useCallback(
    (screenX: number, screenY: number) => {
      const { width, height, scale } = getCanvasScale();
      const x = (screenX * scale) / width * 2 - 1;
      const y = -((screenY * scale) / height) * 2 + 1;
      return { x, y };
    },
    [getCanvasScale]
  );

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      const adapter = (window as any).getLAppAdapter?.();
      if (!adapter || !canvasRef.current) return;

      const model = adapter.getModel();
      const LAppDelegate = getLAppDelegate();
      const view = LAppDelegate?.getInstance?.()?.getView?.();
      if (!view || !model) return;

      const canvas = canvasRef.current;
      const rect = canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;

      const scale = canvas.width / canvas.clientWidth;
      const scaledX = x * scale;
      const scaledY = y * scale;
      const modelX = view._deviceToScreen.transformX(scaledX);
      const modelY = view._deviceToScreen.transformY(scaledY);

      const hitAreaName = model.anyhitTest(modelX, modelY);
      const isHitOnModel = model.isHitOnModel(modelX, modelY);

      if (hitAreaName !== null || isHitOnModel) {
        mouseDownTimeRef.current = Date.now();
        mouseDownPosRef.current = { x: e.clientX, y: e.clientY };
        isPotentialTapRef.current = true;
        setIsDragging(false);

        if (model._modelMatrix) {
          const matrix = model._modelMatrix.getArray();
          modelStartPos.current = { x: matrix[12], y: matrix[13] };
        }
      }
    },
    [canvasRef]
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      const adapter = (window as any).getLAppAdapter?.();
      const LAppDelegate = getLAppDelegate();
      const view = LAppDelegate?.getInstance?.()?.getView?.();
      const model = adapter?.getModel();

      if (
        isPotentialTapRef.current &&
        adapter &&
        view &&
        model &&
        canvasRef.current
      ) {
        const timeElapsed = Date.now() - mouseDownTimeRef.current;
        const deltaX = e.clientX - mouseDownPosRef.current.x;
        const deltaY = e.clientY - mouseDownPosRef.current.y;
        const distanceMoved = Math.sqrt(
          deltaX * deltaX + deltaY * deltaY
        );

        if (
          distanceMoved > DRAG_DISTANCE_THRESHOLD_PX ||
          (timeElapsed > TAP_DURATION_THRESHOLD_MS && distanceMoved > 1)
        ) {
          isPotentialTapRef.current = false;
          setIsDragging(true);

          const canvas = canvasRef.current;
          const rect = canvas.getBoundingClientRect();
          dragStartPos.current = {
            x: mouseDownPosRef.current.x - rect.left,
            y: mouseDownPosRef.current.y - rect.top,
          };
        }
      }

      if (
        isDragging &&
        adapter &&
        view &&
        model &&
        canvasRef.current
      ) {
        const canvas = canvasRef.current;
        const rect = canvas.getBoundingClientRect();
        const currentX = e.clientX - rect.left;
        const currentY = e.clientY - rect.top;

        const scale = canvas.width / canvas.clientWidth;
        const startScaledX = dragStartPos.current.x * scale;
        const startScaledY = dragStartPos.current.y * scale;
        const startModelX = view._deviceToScreen.transformX(startScaledX);
        const startModelY = view._deviceToScreen.transformY(startScaledY);

        const currentScaledX = currentX * scale;
        const currentScaledY = currentY * scale;
        const currentModelX = view._deviceToScreen.transformX(
          currentScaledX
        );
        const currentModelY = view._deviceToScreen.transformY(
          currentScaledY
        );

        const dx = currentModelX - startModelX;
        const dy = currentModelY - startModelY;
        const newX = modelStartPos.current.x + dx;
        const newY = modelStartPos.current.y + dy;

        if (adapter.setModelPosition) {
          adapter.setModelPosition(newX, newY);
        } else if (model._modelMatrix) {
          const matrix = model._modelMatrix.getArray();
          const newMatrix = [...matrix];
          newMatrix[12] = newX;
          newMatrix[13] = newY;
          model._modelMatrix.setMatrix(newMatrix);
        }

        modelPositionRef.current = { x: newX, y: newY };
        setPosition({ x: newX, y: newY });
      }
    },
    [isDragging, canvasRef]
  );

  const handleMouseUp = useCallback(
    (e: React.MouseEvent) => {
      const adapter = (window as any).getLAppAdapter?.();
      const model = adapter?.getModel();
      const LAppDelegate = getLAppDelegate();
      const view = LAppDelegate?.getInstance?.()?.getView?.();

      if (isDragging) {
        setIsDragging(false);
        if (adapter) {
          const currentModel = adapter.getModel();
          if (currentModel && currentModel._modelMatrix) {
            const matrix = currentModel._modelMatrix.getArray();
            const finalPos = { x: matrix[12], y: matrix[13] };
            modelPositionRef.current = finalPos;
            modelStartPos.current = finalPos;
            setPosition(finalPos);
          }
        }
      } else if (
        isPotentialTapRef.current &&
        adapter &&
        model &&
        view &&
        canvasRef.current
      ) {
        const timeElapsed = Date.now() - mouseDownTimeRef.current;
        const deltaX = e.clientX - mouseDownPosRef.current.x;
        const deltaY = e.clientY - mouseDownPosRef.current.y;
        const distanceMoved = Math.sqrt(
          deltaX * deltaX + deltaY * deltaY
        );

        if (
          timeElapsed < TAP_DURATION_THRESHOLD_MS &&
          distanceMoved < DRAG_DISTANCE_THRESHOLD_PX
        ) {
          const allowTapMotion = modelInfo?.pointerInteractive !== false;

          if (allowTapMotion && modelInfo?.tapMotions && canvasRef.current) {
            const canvas = canvasRef.current;
            const rect = canvas.getBoundingClientRect();
            const scale = canvas.width / canvas.clientWidth;
            const downX = (mouseDownPosRef.current.x - rect.left) * scale;
            const downY = (mouseDownPosRef.current.y - rect.top) * scale;
            const modelX = view._deviceToScreen.transformX(downX);
            const modelY = view._deviceToScreen.transformY(downY);

            const hitAreaName = model.anyhitTest(modelX, modelY);
            model.startTapMotion(hitAreaName, modelInfo.tapMotions);
          }
        }
      }

      isPotentialTapRef.current = false;
    },
    [isDragging, canvasRef, modelInfo]
  );

  const handleMouseLeave = useCallback(() => {
    if (isDragging) setIsDragging(false);
    if (isPotentialTapRef.current) isPotentialTapRef.current = false;
  }, [isDragging]);

  // Expose debug functions to window for console testing
  useEffect(() => {
    const playMotion = (
      motionGroup: string,
      motionIndex: number = 0,
      priority: number = 3
    ) => {
      const adapter = (window as any).getLAppAdapter?.();
      if (!adapter) {
        console.error("Live2D adapter not available");
        return false;
      }
      const model = adapter.getModel();
      if (!model) {
        console.error("Live2D model not available");
        return false;
      }
      try {
        console.log(
          `Playing motion: group="${motionGroup}", index=${motionIndex}, priority=${priority}`
        );
        return model.startMotion(motionGroup, motionIndex, priority);
      } catch (error) {
        console.error("Error playing motion:", error);
        return false;
      }
    };

    const playRandomMotion = (motionGroup: string, priority: number = 3) => {
      const adapter = (window as any).getLAppAdapter?.();
      if (!adapter) return false;
      const model = adapter.getModel();
      if (!model) return false;
      try {
        return model.startRandomMotion(motionGroup, priority);
      } catch (error) {
        console.error("Error playing random motion:", error);
        return false;
      }
    };

    const getMotionInfo = () => {
      const adapter = (window as any).getLAppAdapter?.();
      if (!adapter) return null;
      const model = adapter.getModel();
      if (!model) return null;
      try {
        const motionGroups: any[] = [];
        const setting = model._modelSetting;
        if (setting) {
          const groups = setting._json?.FileReferences?.Motions;
          if (groups) {
            for (const groupName in groups) {
              const motions = groups[groupName];
              motionGroups.push({
                name: groupName,
                count: motions.length,
                motions: motions.map((m: any, i: number) => ({
                  index: i,
                  file: m.File,
                })),
              });
            }
          }
        }
        console.log("Available motion groups:", motionGroups);
        return motionGroups;
      } catch (error) {
        console.error("Error getting motion info:", error);
        return null;
      }
    };

    (window as any).Live2DDebug = { playMotion, playRandomMotion, getMotionInfo };
    console.log(
      'Live2D Debug functions exposed to window.Live2DDebug. Type Live2DDebug.help() for usage.'
    );

    return () => {
      delete (window as any).Live2DDebug;
    };
  }, []);

  return {
    position,
    isDragging,
    handlers: {
      onMouseDown: handleMouseDown,
      onMouseMove: handleMouseMove,
      onMouseUp: handleMouseUp,
      onMouseLeave: handleMouseLeave,
    },
  };
};