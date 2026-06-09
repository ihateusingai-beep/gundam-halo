/**
 * CSS Avatar — pure CSS/SVG NT-D themed avatar.
 *
 * Replaces the Live2D canvas when no model is loaded.
 * Listens to `live2d.trigger` WS events and transitions
 * between emotion states via CSS class changes.
 *
 * Emotion → CSS class mapping (mirrors EMOTION_MAP in halo_responder.py):
 *   calm      → .avatar--calm
 *   focused   → .avatar--focused
 *   awakening → .avatar--psychoframe
 *   alert     → .avatar--alert
 *   damage    → .avatar--damage
 *   resolve   → .avatar--resolve
 *   jubilant  → .avatar--jubilant
 *   stealth   → .avatar--stealth
 */

import { useEffect, useRef } from "react";
import { subscribeToVoice } from "@/services/halo-live2d-bridge";

interface AvatarProps {
  emotion?: string;
  /** Show scan line overlay (for active/speaking state) */
  active?: boolean;
}

const EMOTION_CLASS: Record<string, string> = {
  calm: "avatar--calm",
  focused: "avatar--focused",
  awakening: "avatar--psychoframe",
  alert: "avatar--alert",
  damage: "avatar--damage",
  resolve: "avatar--resolve",
  jubilant: "avatar--jubilant",
  stealth: "avatar--stealth",
};

export function CSSAvatar({ emotion, active }: AvatarProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Subscribe to live2d.trigger WS events
  useEffect(() => {
    const unsubscribe = subscribeToVoice("live2d.trigger", (event) => {
      if (!containerRef.current) return;
      const emo = (event as any).data?.emotion as string;

      // Remove all emotion classes
      const allClasses = Object.values(EMOTION_CLASS);
      containerRef.current.classList.remove(...allClasses);

      // Add new emotion class
      const cls = EMOTION_CLASS[emo] || EMOTION_CLASS.calm;
      containerRef.current.classList.add(cls);
    });

    return unsubscribe;
  }, []);

  // Also apply initial emotion prop
  useEffect(() => {
    if (!containerRef.current || !emotion) return;
    const allClasses = Object.values(EMOTION_CLASS);
    containerRef.current.classList.remove(...allClasses);
    const cls = EMOTION_CLASS[emotion] || EMOTION_CLASS.calm;
    containerRef.current.classList.add(cls);
  }, [emotion]);

  return (
    <div
      ref={containerRef}
      className={`avatar avatar--calm${active ? " avatar--active" : ""}`}
      aria-label={`NT-D Avatar — ${emotion ?? "calm"}`}
    >
      {/* Hex frame */}
      <div className="avatar__frame">
        {/* Corner brackets */}
        <span className="avatar__bracket avatar__bracket--tl" />
        <span className="avatar__bracket avatar__bracket--tr" />
        <span className="avatar__bracket avatar__bracket--bl" />
        <span className="avatar__bracket avatar__bracket--br" />

        {/* Scan line */}
        {active && <div className="avatar__scan" />}

        {/* Main face */}
        <div className="avatar__face">
          {/* Head silhouette */}
          <div className="avatar__head">
            {/* VFin antenna */}
            <div className="avatar__antenna avatar__antenna--left" />
            <div className="avatar__antenna avatar__antenna--right" />

            {/* Psychoframe visor */}
            <div className="avatar__visor">
              <div className="avatar__eye avatar__eye--left" />
              <div className="avatar__eye avatar__eye--right" />
            </div>

            {/* Psychoframe mouth */}
            <div className="avatar__mouth" />
          </div>

          {/* Psychoframe border glow */}
          <div className="avatar__glow" />
        </div>

        {/* Status text */}
        <div className="avatar__status">RX-0</div>
      </div>
    </div>
  );
}