/**
 * Live2D Canvas component for Gundam Halo cockpit dashboard
 * adapted from Open-LLM-VTuber (stripped Electron IPC, pet mode dependencies)
 */
import { memo, useRef } from "react";
import { useLive2DConfig } from "@/context/live2d-config-context";
import { useLive2DModel } from "@/hooks/canvas/use-live2d-model";
import { useLive2DResize } from "@/hooks/canvas/use-live2d-resize";

interface Live2DCanvasProps {
  showSidebar?: boolean;
}

export const Live2DCanvas = memo(
  ({ showSidebar }: Live2DCanvasProps): React.ReactElement => {
    const { modelInfo } = useLive2DConfig();
    const internalContainerRef = useRef<HTMLDivElement>(null);

    const { canvasRef } = useLive2DResize({
      containerRef: internalContainerRef,
      modelInfo,
      showSidebar,
    });

    const { isDragging, handlers } = useLive2DModel({
      modelInfo,
      canvasRef,
    });

    return (
      <div
        ref={internalContainerRef}
        className="w-full h-full overflow-hidden relative"
        style={{ pointerEvents: "auto" }}
        {...handlers}
      >
        <canvas
          id="canvas"
          ref={canvasRef}
          className="w-full h-full block"
          style={{ cursor: isDragging ? "grabbing" : "default" }}
        />
      </div>
    );
  }
);

Live2DCanvas.displayName = "Live2DCanvas";