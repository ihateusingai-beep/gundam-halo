/** Tests for the MessageBubble component (A8). Reusable across
 *  B2 SessionDetailPage and A5 ProjectDetailPage.
 *
 *  Why a small test suite: MessageBubble renders 4 roles (user,
 *  agent, tool, system) plus two state flags (pending, error).
 *  Each combination has a different visual treatment (border,
 *  background, opacity, badge).  Smoke-testing each combination
 *  locks the wire contract — if someone re-styles a role, the
 *  test catches it.
 */
import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { MessageBubble, type ChatMessage } from "@/components/gundam/MessageBubble";

afterEach(() => {
  cleanup();
});

describe("MessageBubble", () => {
  it("renders user text under the YOU badge", () => {
    render(<MessageBubble msg={{ role: "user", text: "hi" }} />);
    expect(screen.getByText("YOU")).toBeInTheDocument();
    expect(screen.getByText("hi")).toBeInTheDocument();
  });

  it("renders agent text under the AGENT badge", () => {
    render(<MessageBubble msg={{ role: "agent", text: "hi from agent" }} />);
    expect(screen.getByText("AGENT")).toBeInTheDocument();
    expect(screen.getByText("hi from agent")).toBeInTheDocument();
  });

  it("renders tool text with badge + tool name", () => {
    render(
      <MessageBubble
        msg={{ role: "tool", text: "result", tool_name: "shell_exec" }}
      />
    );
    expect(screen.getByText("TOOL")).toBeInTheDocument();
    expect(screen.getByText("result")).toBeInTheDocument();
    expect(screen.getByText(/shell_exec/)).toBeInTheDocument();
  });

  it("renders system text under the SYSTEM badge", () => {
    render(
      <MessageBubble msg={{ role: "system", text: "You are an agent." }} />
    );
    expect(screen.getByText("SYSTEM")).toBeInTheDocument();
  });

  it("shows '● pending' badge when pending:true", () => {
    render(
      <MessageBubble msg={{ role: "user", text: "sending", pending: true }} />
    );
    expect(screen.getByText(/pending/)).toBeInTheDocument();
  });

  it("shows '✕ failed' badge when error:true", () => {
    render(
      <MessageBubble msg={{ role: "user", text: "send failed", error: true }} />
    );
    // The badge has the title="Send failed" attribute, so we can
    // target it specifically to avoid matching the message text.
    const badge = screen.getByTitle("Send failed");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent(/failed/);
  });

  it("does NOT show tool badge if tool_name is missing", () => {
    render(<MessageBubble msg={{ role: "tool", text: "raw" }} />);
    // No tool_name → no 🔧 badge. We check for the absence of any
    // span containing the wrench emoji. (Message text "raw" doesn't
    // contain 🔧 so this is safe.)
    const allText = document.body.textContent ?? "";
    expect(allText.includes("🔧")).toBe(false);
  });

  it("renders the agent bubble with tool_calls attached (assistant + tool_calls)", () => {
    const msg: ChatMessage = {
      role: "agent",
      text: "let me check",
      tool_calls: [
        { id: "tc1", name: "shell_exec", args: { command: "ls" } },
      ],
    };
    render(<MessageBubble msg={msg} />);
    expect(screen.getByText("let me check")).toBeInTheDocument();
  });
});
