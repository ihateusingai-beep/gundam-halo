/**
 * Breadcrumb.test.tsx — Sprint 49 #6 verification.
 *
 * 2 tests pinning: hidden on `/`; segments for a nested route.
 */
import { describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router";
import { render, screen } from "@testing-library/react";

import { Breadcrumb } from "./Breadcrumb";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Breadcrumb />
    </MemoryRouter>,
  );
}

describe("Breadcrumb", () => {
  it("hides itself on the home route", () => {
    const { container } = renderAt("/");
    expect(container.querySelector("[data-testid=breadcrumb]")).toBeNull();
  });

  it("renders segments for a nested route", () => {
    renderAt("/projects/halo/memory");
    // Home link is always present for nested routes
    expect(screen.getByRole("link", { name: /Home/ })).toBeInTheDocument();
    // Segments (last is the current page, rendered as <span aria-current>)
    const current = screen.getByText("memory");
    expect(current.getAttribute("aria-current")).toBe("page");
    // Intermediates are clickable links
    const projectsLink = screen.getByRole("link", { name: "projects" });
    expect(projectsLink.getAttribute("href")).toBe("/projects");
  });
});
