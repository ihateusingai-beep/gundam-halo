/** Tests for the message wire-format mapper (used by B2 SessionDetailPage
 *  and A5 ProjectDetailPage). Pure, no React, no globals.
 */
import { describe, it, expect } from "vitest";
import { mapMessages, type BackendMessage } from "@/lib/message-mapper";

describe("mapMessages", () => {
  it("passes user messages through with content → text", () => {
    const out = mapMessages([{ role: "user", content: "hello" }]);
    expect(out).toEqual([{ role: "user", text: "hello" }]);
  });

  it("passes system messages through with content → text", () => {
    const out = mapMessages([{ role: "system", content: "You are an agent." }]);
    expect(out).toEqual([{ role: "system", text: "You are an agent." }]);
  });

  it("translates assistant → agent", () => {
    const out = mapMessages([{ role: "assistant", content: "hi" }]);
    expect(out).toEqual([{ role: "agent", text: "hi" }]);
  });

  it("attaches tool_calls to the agent bubble when assistant has them", () => {
    const out = mapMessages([
      {
        role: "assistant",
        content: "let me check",
        tool_calls: [
          { id: "tc1", name: "shell_exec", arguments: { command: "ls" } },
        ],
      },
    ]);
    expect(out).toHaveLength(1);
    expect(out[0].role).toBe("agent");
    expect(out[0].text).toBe("let me check");
    expect(out[0].tool_calls).toEqual([
      { id: "tc1", name: "shell_exec", args: { command: "ls" } },
    ]);
  });

  it("does not attach tool_calls key when assistant has none", () => {
    const out = mapMessages([{ role: "assistant", content: "no tools" }]);
    expect(out[0]).toEqual({ role: "agent", text: "no tools" });
    expect(out[0]).not.toHaveProperty("tool_calls");
  });

  it("defaults missing arguments to empty object", () => {
    const out = mapMessages([
      {
        role: "assistant",
        content: "",
        tool_calls: [
          { id: "tc1", name: "noop", arguments: undefined as unknown as Record<string, never> },
        ],
      },
    ]);
    // The mapper does `tc.arguments ?? {}` so a missing arg becomes {}.
    expect(out[0].tool_calls?.[0].args).toEqual({});
  });

  it("translates tool messages with name → tool_name", () => {
    const out = mapMessages([
      { role: "tool", content: "result text", name: "shell_exec" },
    ]);
    expect(out).toEqual([
      { role: "tool", text: "result text", tool_name: "shell_exec" },
    ]);
  });

  it("tool messages without name get no tool_name", () => {
    const out = mapMessages([{ role: "tool", content: "raw" }]);
    expect(out).toEqual([{ role: "tool", text: "raw" }]);
    expect(out[0]).not.toHaveProperty("tool_name");
  });

  it("empty tool content becomes '(no result)'", () => {
    const out = mapMessages([{ role: "tool", content: "", name: "x" }]);
    expect(out[0].text).toBe("(no result)");
  });

  it("empty user/system/assistant content becomes empty string", () => {
    const out = mapMessages([
      { role: "user", content: "" },
      { role: "system", content: "" },
      { role: "assistant", content: "" },
    ]);
    expect(out.map((m) => m.text)).toEqual(["", "", ""]);
  });

  it("preserves order across mixed roles", () => {
    const raw: BackendMessage[] = [
      { role: "user", content: "1" },
      { role: "assistant", content: "2" },
      { role: "tool", content: "3", name: "x" },
      { role: "assistant", content: "4" },
      { role: "user", content: "5" },
    ];
    const out = mapMessages(raw);
    expect(out.map((m) => m.role)).toEqual([
      "user",
      "agent",
      "tool",
      "agent",
      "user",
    ]);
    expect(out.map((m) => m.text)).toEqual(["1", "2", "3", "4", "5"]);
  });

  it("returns empty array for empty input", () => {
    expect(mapMessages([])).toEqual([]);
  });
});
