/**
 * Live2D expression control hook
 * adapted from Open-LLM-VTuber for Gundam Halo
 */
import { useCallback } from "react";
import { ModelInfo } from "@/context/live2d-types";

/**
 * Set expression for Live2D model
 */
export const setExpression = (
  expressionValue: string | number,
  lappAdapter: any,
  logMessage?: string
) => {
  try {
    if (typeof expressionValue === "string") {
      lappAdapter.setExpression(expressionValue);
    } else if (typeof expressionValue === "number") {
      const expressionName = lappAdapter.getExpressionName(expressionValue);
      if (expressionName) {
        lappAdapter.setExpression(expressionName);
      }
    }
    if (logMessage) console.log(logMessage);
  } catch (error) {
    console.error("Failed to set expression:", error);
  }
};

/**
 * Reset expression to default
 */
export const resetExpression = (
  lappAdapter: any,
  modelInfo?: ModelInfo
) => {
  if (!lappAdapter) return;

  try {
    const model = lappAdapter.getModel();
    if (!model || !model._modelSetting) {
      console.log(
        "Model or model settings not loaded yet, skipping expression reset"
      );
      return;
    }

    // Use defaultEmotion if defined
    if (modelInfo?.defaultEmotion !== undefined) {
      setExpression(
        modelInfo.defaultEmotion,
        lappAdapter,
        `Reset expression to default: ${modelInfo.defaultEmotion}`
      );
    } else {
      // Fall back to first expression
      const expressionCount = lappAdapter.getExpressionCount();
      if (expressionCount > 0) {
        const defaultExpressionName = lappAdapter.getExpressionName(0);
        if (defaultExpressionName) {
          setExpression(defaultExpressionName, lappAdapter);
        }
      }
    }
  } catch (error) {
    console.log("Failed to reset expression:", error);
  }
};

export function useLive2DExpression() {
  const _setExpression = useCallback(
    (expressionValue: string | number, lappAdapter: any, logMessage?: string) => {
      setExpression(expressionValue, lappAdapter, logMessage);
    },
    []
  );

  const _resetExpression = useCallback(
    (lappAdapter: any, modelInfo?: ModelInfo) => {
      resetExpression(lappAdapter, modelInfo);
    },
    []
  );

  return {
    setExpression: _setExpression,
    resetExpression: _resetExpression,
  };
}