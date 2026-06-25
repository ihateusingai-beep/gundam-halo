/**
 * StepTailscale.test.tsx — Sprint 44 acceptance test #5.
 *
 * Verifies the "Skip for now" button submits with enabled=false.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StepTailscale } from "@/components/wizard/StepTailscale";

afterEach(() => cleanup());

describe("StepTailscale", () => {
  it("clicking Skip for now submits with enabled=false", async () => {
    const submitMock = vi.fn().mockResolvedValue(undefined);

    render(
      <StepTailscale
        form={{ enabled: false, hostname: "gundam-halo" }}
        onSubmit={submitMock}
        errors={[]}
        busy={false}
      />,
    );

    // window.confirm returns true by default in jsdom.
    screen.getByTestId("tailscale-skip").click();

    await waitFor(() => {
      expect(submitMock).toHaveBeenCalledTimes(1);
    });

    const [arg] = submitMock.mock.calls[0];
    expect(arg).toEqual({ enabled: false, hostname: "gundam-halo" });
  });
});
