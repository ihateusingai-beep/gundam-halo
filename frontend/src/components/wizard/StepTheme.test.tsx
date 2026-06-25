/**
 * StepTheme.test.tsx — Sprint 44 acceptance test #4.
 *
 * Verifies clicking a theme card applies it via
 * document.documentElement.setAttribute('data-theme', …).
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StepTheme } from "@/components/wizard/StepTheme";

beforeEach(() => {
  document.documentElement.setAttribute("data-theme", "gundam-ntd");
});

afterEach(() => cleanup());

describe("StepTheme", () => {
  it("clicking a theme card applies it via data-theme attribute", () => {
    const onChangeMock = vi.fn().mockResolvedValue(undefined);

    render(
      <StepTheme
        form={{ themeId: "gundam-ntd" }}
        onChange={onChangeMock}
        errors={[]}
        busy={false}
      />,
    );

    // Click "Gundam SEED".
    const seedCard = screen.getByTestId("theme-gundam-seed");
    seedCard.click();

    expect(document.documentElement.getAttribute("data-theme")).toBe(
      "gundam-seed",
    );
    expect(onChangeMock).toHaveBeenCalledWith({ themeId: "gundam-seed" });
  });

  it("renders all 8 theme cards", () => {
    render(
      <StepTheme
        form={{ themeId: "gundam-ntd" }}
        onChange={vi.fn()}
        errors={[]}
        busy={false}
      />,
    );

    const themeIds = [
      "gundam-ntd",
      "gundam-god",
      "gundam-seed",
      "gundam-crossbone",
      "gundam-destiny",
      "gundam-halo",
      "gundam-ntd-green",
      "gundam-cartoon",
    ];
    for (const id of themeIds) {
      expect(screen.getByTestId(`theme-${id}`)).toBeTruthy();
    }
  });
});
