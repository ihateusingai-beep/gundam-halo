/**
 * Wire-format → ChatMessage mapper, shared by ProjectDetailPage (A5)
 * and SessionDetailPage (B2).
 *
 * Why a shared mapper:
 *   The backend speaks OpenAI-style message dicts
 *   (`role: "assistant" | "tool" | "user" | "system"`, `tool_calls`
 *   as `{id, name, arguments}`, etc.) but the dashboard UI uses a
 *   normalized shape: `role: "agent" | "tool" | "user" | "system"`,
 *   `text` (renamed from `content`), `tool_name` (from `name`).
 *
 *   Both ProjectDetailPage (live chat) and SessionDetailPage (replay)
 *   consume the same wire shape, so the mapping logic lives here.
 *
 *   Keeping it a pure function (no React, no globals) means it can be
 *   unit-tested in isolation and reused anywhere we receive a
 *   backend message list — `/api/projects/:name/memory/:sessionId`
 *   (B2) and `/api/sessions/:id/messages` (A5) return identical
 *   message shapes, so the same mapper works for both.
 */

import type { ChatMessage } from "@/components/gundam/MessageBubble";

export interface BackendMessage {
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  tool_calls?: Array<{ id: string; name: string; arguments: Record<string, any> }>;
  tool_call_id?: string;
  name?: string;
}

/** Translate a list of backend messages to UI ChatMessages.
 *
 *  - `assistant` (with or without tool_calls) → `agent` bubble
 *  - `tool` → `tool` bubble, badge from `name`
 *  - `user` / `system` → pass through, with `content` → `text`
 */
export function mapMessages(raw: BackendMessage[]): ChatMessage[] {
  return raw.map((m) => {
    if (m.role === "assistant") {
      return {
        role: "agent" as const,
        text: m.content || "",
        ...(m.tool_calls && m.tool_calls.length > 0
          ? {
              tool_calls: m.tool_calls.map((tc) => ({
                id: tc.id,
                name: tc.name,
                args: tc.arguments ?? {},
              })),
            }
          : {}),
      };
    }
    if (m.role === "tool") {
      return {
        role: "tool" as const,
        text: m.content || "(no result)",
        ...(m.name ? { tool_name: m.name } : {}),
      };
    }
    return {
      role: m.role as "user" | "system",
      text: m.content || "",
    };
  });
}
