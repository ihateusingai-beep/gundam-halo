/**
 * Copyright(c) Live2D Inc. All rights reserved.
 * Live2D emotion mapping interface
 */
export interface EmotionMap {
  [key: string]: number | string;
}

/**
 * Motion weight mapping interface
 */
export interface MotionWeightMap {
  [key: string]: number;
}

/**
 * Tap motion mapping interface
 */
export interface TapMotionMap {
  [key: string]: MotionWeightMap;
}

/**
 * Live2D model information interface
 * Defines a model loaded from .model3.json + emotion/motion mapping
 */
export interface ModelInfo {
  /** Model name */
  name?: string;

  /** Model description */
  description?: string;

  /** Model URL (relative to baseUrl, e.g. /models/hiyori/hiyori.model3.json) */
  url: string;

  /** Scale factor (kScale in Open-LLM-VTuber) */
  kScale: number;

  /** Initial X position shift (logical pixels) */
  initialXshift: number;

  /** Initial Y position shift (logical pixels) */
  initialYshift: number;

  /** Idle motion group name (e.g. "Idle") */
  idleMotionGroupName?: string;

  /** Default emotion (expression name or index) */
  defaultEmotion?: number | string;

  /** Emotion mapping: emotion key -> expression name/index */
  emotionMap: EmotionMap;

  /** Enable pointer interactivity (drag, tap) */
  pointerInteractive?: boolean;

  /** Tap motion mapping: hit area -> motion group */
  tapMotions?: TapMotionMap;

  /** Enable scroll to resize */
  scrollToResize?: boolean;

  /** Initial scale */
  initialScale?: number;
}