/**
 * card.test.tsx — Sprint 62 U-A2 tests.
 *
 * 5 tests pinning the Card primitive contract: renders with
 * data-slot, sub-components render, action accepts children,
 * class merging works.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "./card";

describe("Card (Sprint 62 U-A2)", () => {
  afterEach(() => cleanup());

  it("Card renders with data-slot='card'", () => {
    render(<Card data-testid="card">Body</Card>);
    const card = screen.getByTestId("card");
    expect(card.getAttribute("data-slot")).toBe("card");
  });

  it("Header / Title / Description / Content / Footer render", () => {
    render(
      <Card>
        <CardHeader>
          <CardTitle>Title</CardTitle>
          <CardDescription>Subtitle</CardDescription>
        </CardHeader>
        <CardContent>Body</CardContent>
        <CardFooter>Foot</CardFooter>
      </Card>,
    );
    expect(screen.getByText("Title").getAttribute("data-slot")).toBe(
      "card-title",
    );
    expect(screen.getByText("Subtitle").getAttribute("data-slot")).toBe(
      "card-description",
    );
    expect(screen.getByText("Body").getAttribute("data-slot")).toBe(
      "card-content",
    );
    expect(screen.getByText("Foot").getAttribute("data-slot")).toBe(
      "card-footer",
    );
  });

  it("CardAction renders children + data-slot", () => {
    render(
      <Card>
        <CardHeader>
          <CardTitle>Title</CardTitle>
          <CardAction>
            <button data-testid="action-btn">Click</button>
          </CardAction>
        </CardHeader>
      </Card>,
    );
    expect(screen.getByTestId("action-btn")).toBeTruthy();
    expect(screen.getByText("Click").getAttribute("data-slot")).toBeNull();
  });

  it("class merging: custom className is appended", () => {
    render(
      <Card className="my-custom-class" data-testid="card">
        Body
      </Card>,
    );
    expect(screen.getByTestId("card").className).toContain("my-custom-class");
  });

  it("Card renders without leaking gundam-specific data-theme", () => {
    render(<Card data-testid="card">Body</Card>);
    const card = screen.getByTestId("card");
    expect(card.getAttribute("data-theme")).toBeNull();
  });
});