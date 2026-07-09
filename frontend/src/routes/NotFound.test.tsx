/**
 * NotFound.test.tsx — Sprint 60 R-A3 tests.
 *
 * 4 tests pinning the 404 page contract:
 *   1. Renders "404" headline + URL echo
 *   2. "Back to Cockpit" link with href="/"
 *   3. URL echo reflects useLocation()
 *   4. Renders inside a Router (required for <Link>)
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";

import { NotFoundPage } from "./NotFound";

describe("NotFoundPage (Sprint 60 R-A3)", () => {
  afterEach(() => cleanup());

  it("renders the 404 panel + URL echo", () => {
    render(
      <MemoryRouter initialEntries={["/missing/path"]}>
        <Routes>
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByTestId("not-found")).toBeTruthy();
    expect(screen.getByText(/404/)).toBeTruthy();
    expect(screen.getByTestId("not-found-path").textContent).toBe(
      "/missing/path",
    );
  });

  it("'Back to Cockpit' link points to '/'", () => {
    render(
      <MemoryRouter initialEntries={["/typo-here"]}>
        <Routes>
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </MemoryRouter>,
    );
    const link = screen.getByTestId("not-found-home-link");
    expect(link.getAttribute("href")).toBe("/");
    expect(link.textContent).toMatch(/Back to Cockpit/);
  });

  it("URL echo updates with useLocation (different paths render different echoes)", () => {
    render(
      <MemoryRouter initialEntries={["/foo/bar/baz"]}>
        <Routes>
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByTestId("not-found-path").textContent).toBe(
      "/foo/bar/baz",
    );
  });

  it("renders the cockpit-shell-safe 'data-testid' root + Heading", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByTestId("not-found")).toBeTruthy();
    expect(screen.getByRole("heading", { level: 1 })?.textContent).toMatch(
      /Route not found/i,
    );
  });
});