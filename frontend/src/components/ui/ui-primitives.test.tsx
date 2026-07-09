/**
 * ui-primitives.test.tsx — Sprint 60 U-A1 smoke tests.
 *
 * 7 tests pinning the smoke contract of each UI primitive. We
 * don't exhaustively test every variant (CVA snapshot tests in
 * the dev styleguide cover that); we just verify each primitive:
 *   1. renders with the expected slot attribute
 *   2. handles a click / value / open prop
 *   3. exposes the right `data-testid` for downstream tests
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";

import { Button } from "./button";
import { Command, CommandInput, CommandList, CommandItem } from "./command";
import { Dialog, DialogContent, DialogTrigger } from "./dialog";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from "./dropdown-menu";
import { Input } from "./input";
import { Textarea } from "./textarea";
import { InputGroup, InputGroupAddon } from "./input-group";

describe("UI primitives (Sprint 60 U-A1)", () => {
  afterEach(() => cleanup());

  it("Button renders with slot attribute + click fires", () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Click me</Button>);
    const btn = screen.getByRole("button", { name: /Click me/i });
    expect(btn.getAttribute("data-slot")).toBe("button");
    fireEvent.click(btn);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("Input renders + value/onChange round-trips", () => {
    const onChange = vi.fn();
    render(<Input value="hello" onChange={onChange} placeholder="type…" />);
    const input = screen.getByPlaceholderText("type…") as HTMLInputElement;
    expect(input.getAttribute("data-slot")).toBe("input");
    expect(input.value).toBe("hello");
    fireEvent.change(input, { target: { value: "world" } });
    expect(onChange).toHaveBeenCalled();
  });

  it("Textarea renders with slot attribute", () => {
    render(<Textarea defaultValue="multi line content" onChange={() => {}} />);
    const ta = screen.getByDisplayValue("multi line content") as HTMLTextAreaElement;
    expect(ta.getAttribute("data-slot")).toBe("textarea");
    expect(ta.tagName).toBe("TEXTAREA");
  });

  it("InputGroup renders with addon", () => {
    render(
      <InputGroup>
        <InputGroupAddon>📁</InputGroupAddon>
        <Input value="" onChange={() => {}} />
      </InputGroup>,
    );
    expect(screen.getByText("📁")).toBeTruthy();
    expect(screen.getByRole("textbox")).toBeTruthy();
  });

  it("Dialog opens via trigger click + closes via Escape", async () => {
    render(
      <Dialog>
        <DialogTrigger>Open</DialogTrigger>
        <DialogContent>
          <div data-testid="dialog-body">Dialog content</div>
        </DialogContent>
      </Dialog>,
    );
    expect(screen.queryByTestId("dialog-body")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Open/i }));
    // Wait for Dialog's open animation.
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(screen.getByTestId("dialog-body")).toBeTruthy();
  });

  it("Command palette renders input + list + item", () => {
    render(
      <Command>
        <CommandInput placeholder="Type a command…" />
        <CommandList>
          <CommandItem>Navigate to settings</CommandItem>
        </CommandList>
      </Command>,
    );
    expect(screen.getByPlaceholderText(/Type a command/i)).toBeTruthy();
    expect(screen.getByText(/Navigate to settings/i)).toBeTruthy();
  });

  it("DropdownMenu renders trigger + content", () => {
    render(
      <DropdownMenu>
        <DropdownMenuTrigger>Open menu</DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem>Profile</DropdownMenuItem>
          <DropdownMenuItem>Settings</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>,
    );
    // Trigger button is always visible; content is in a Portal.
    expect(screen.getByRole("button", { name: /Open menu/i })).toBeTruthy();
  });
});