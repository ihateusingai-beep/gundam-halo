/**
 * Live2D model resize + scale hook
 * adapted from Open-LLM-VTuber for Gundam Halo
 * (stripped Electron/useMode dependencies)
 *
 * WebSDK is loaded via <script> tags. Access via window globals.
 */
// @ts-nocheck
/* eslint-disable no-use-before-define */
/* eslint-disable @typescript-eslint/ban-ts-comment */
/* eslint-disable no-underscore-dangle */
import { useEffect, useCallback, useRef } from "react";
import { ModelInfo } from "@/context/live2d-types";

// Access WebSDK via window globals
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const getLAppDelegate = () => (window as any).LAppDelegate;
const getLAppLive2DManager = () => (window as any).LAppLive2DManager;

const MIN_SCALE = 0.1;
const MAX_SCALE = 5.0;
const EASING_FACTOR = 0.3;
const WHEEL_SCALE_STEP = 0.03;
const DEFAULT_SCALE = 1.0;

interface UseLive2DResizeProps {
  containerRef: React.RefObject<HTMLDivElement | null>;
  modelInfo?: ModelInfo;
  showSidebar?: boolean;
}

export const applyScale = (scale: number) => {
  try {
    const manager = getLAppLive2DManager();
    if (!manager?.getInstance) return;
    const inst = manager.getInstance();
    if (!inst) return;
    const model = inst.getModel?.(0);
    if (!model) return;
    // @ts-ignore
    model._modelMatrix.scale(scale, scale);
  } catch {
    console.debug("Model not ready for scaling yet");
  }
};

export const useLive2DResize = ({
  containerRef,
  modelInfo,
  showSidebar,
}: UseLive2DResizeProps) => {
  const animationFrameIdRef = useRef<number | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const isResizingRef = useRef<boolean>(false);
  const lastScaleRef = useRef<number>(modelInfo?.kScale || DEFAULT_SCALE);
  const targetScaleRef = useRef<number>(modelInfo?.kScale || DEFAULT_SCALE);
  const animationFrameRef = useRef<number>();
  const isAnimatingRef = useRef<boolean>(false);
  const lastContainerDimensionsRef = useRef<{ width: number; height: number }>({
    width: 0,
    height: 0,
  });
  const prevSidebarStateRef = useRef<boolean | undefined>(showSidebar);

  useEffect(() => {
    const newInitialScale = modelInfo?.kScale || DEFAULT_SCALE;
    lastScaleRef.current = newInitialScale;
    targetScaleRef.current = newInitialScale;

    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      isAnimatingRef.current = false;
    }

    const handle = requestAnimationFrame(() => {
      handleResize();
    });
    return () => cancelAnimationFrame(handle);
  }, [modelInfo?.url, modelInfo?.kScale]);

  const animateEase = useCallback(() => {
    const clampedTargetScale = Math.max(
      MIN_SCALE,
      Math.min(MAX_SCALE, targetScaleRef.current)
    );
    const currentScale = lastScaleRef.current;
    const diff = clampedTargetScale - currentScale;
    const newScale = currentScale + diff * EASING_FACTOR;
    applyScale(newScale);
    lastScaleRef.current = newScale;
    animationFrameRef.current = requestAnimationFrame(animateEase);
  }, []);

  const handleWheel = useCallback(
    (e: WheelEvent) => {
      e.preventDefault();
      if (!modelInfo?.scrollToResize) return;

      const direction = e.deltaY > 0 ? -1 : 1;
      const increment = WHEEL_SCALE_STEP * direction;
      const newTargetScale = Math.max(
        MIN_SCALE,
        Math.min(MAX_SCALE, lastScaleRef.current + increment)
      );
      targetScaleRef.current = newTargetScale;

      if (!isAnimatingRef.current) {
        isAnimatingRef.current = true;
        animationFrameRef.current = requestAnimationFrame(animateEase);
      }
    },
    [modelInfo?.scrollToResize, animateEase]
  );

  const handleResize = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    isResizingRef.current = true;

    try {
      const containerBounds = containerRef.current?.getBoundingClientRect();
      const width = containerBounds?.width ?? 0;
      const height = containerBounds?.height ?? 0;

      const lastDimensions = lastContainerDimensionsRef.current;
      const sidebarChanged = prevSidebarStateRef.current !== showSidebar;
      const dimensionsChanged =
        Math.abs(lastDimensions.width - width) > 1 ||
        Math.abs(lastDimensions.height - height) > 1;
      const hasChanged = dimensionsChanged || sidebarChanged;

      if (!hasChanged) {
        isResizingRef.current = false;
        return;
      }

      lastContainerDimensionsRef.current = { width, height };
      prevSidebarStateRef.current = showSidebar;

      if (width === 0 || height === 0) {
        isResizingRef.current = false;
        return;
      }

      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;

      const LAppDelegate = getLAppDelegate();
      const delegate = LAppDelegate?.getInstance?.();
      if (delegate) {
        delegate.onResize?.();
      }

      isResizingRef.current = false;
    } catch {
      isResizingRef.current = false;
    }
  }, [containerRef, showSidebar]);

  useEffect(() => {
    if (prevSidebarStateRef.current !== showSidebar) {
      if (animationFrameIdRef.current !== null)
        cancelAnimationFrame(animationFrameIdRef.current);
      animationFrameIdRef.current = requestAnimationFrame(() => {
        handleResize();
        animationFrameIdRef.current = null;
      });
    }
  }, [showSidebar, handleResize]);

  useEffect(() => {
    const canvasElement = canvasRef.current;
    if (canvasElement) {
      canvasElement.addEventListener("wheel", handleWheel, { passive: false });
      return () => canvasElement.removeEventListener("wheel", handleWheel);
    }
    return undefined;
  }, [handleWheel]);

  useEffect(() => {
    return () => {
      if (animationFrameRef.current)
        cancelAnimationFrame(animationFrameRef.current);
      if (animationFrameIdRef.current !== null)
        cancelAnimationFrame(animationFrameIdRef.current);
    };
  }, []);

  useEffect(() => {
    const containerElement = containerRef.current;
    if (!containerElement) return undefined;

    const raf = requestAnimationFrame(() => handleResize());
    const observer = new ResizeObserver(() => {
      if (!isResizingRef.current) {
        const rafId = requestAnimationFrame(() => handleResize());
        animationFrameIdRef.current = rafId;
      }
    });
    observer.observe(containerElement);

    return () => {
      if (animationFrameIdRef.current !== null)
        cancelAnimationFrame(animationFrameIdRef.current);
      observer.disconnect();
    };
  }, [containerRef, handleResize]);

  return { canvasRef, handleResize };
};