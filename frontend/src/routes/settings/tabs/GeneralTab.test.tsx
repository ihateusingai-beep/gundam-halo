/**
 * GeneralTab.test.tsx — Sprint 72 X-A1g.
 *
 * Mounts the General settings tab (LLM brain + server +
 * user + paths). Aims to bump `GeneralTab.tsx` coverage
 * from 2.56% to ~60% (Sprint 72 X-A1g coverage ratchet;
 * target: line coverage ≥60%).
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GeneralTab } from "./GeneralTab";
import type { Settings } from "@/types/api";

const TEST_SETTINGS: Settings = {
  app: {
    version: "0.3.13",
    home: "/Users/pilot/.gundam-halo",
    config_path: "/Users/pilot/.gundam-halo/config.toml",
  },
  user: {
    name: "Pilot",
    default_theme: "gundam-ntd",
  },
  llm: {
    provider: "minimax",
    base_url: "https://api.example.com",
    default_model: "MiniMax-Text-01",
    fallback_model: "MiniMax-Text-01",
    api_key_configured: true,
  },
  server: {
    host: "127.0.0.1",
    port: 8765,
    log_level: "INFO",
    require_tailscale: false,
    tailscale_hostname: "",
  },
  mac: {
    default_path_policy: "project_only",
    file_read_paths: ["~/projects/**"],
    file_write_paths: ["~/projects/output/**"],
    shell_allowlist: ["ls", "cat"],
    apple_script_enabled: true,
    notifications_enabled: true,
    a11y_enabled: false,
  },
  telegram: {
    enabled: false,
    allowed_chat_ids: [],
    command_prefix: "/gundam",
    bot_token_configured: false,
  },
  security: {
    audit_log: "audit.log",
    audit_max_size_mb: 10,
    injection_scan: true,
    require_confirm_for: [],
  },
};

afterEach(() => {
  cleanup();
});

describe("GeneralTab (mount with prop)", () => {
  it("renders the section headings (LLM, Server, User)", () => {
    render(<GeneralTab settings={TEST_SETTINGS} />);
    expect(screen.getAllByText(/LLM/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Server/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/User/).length).toBeGreaterThanOrEqual(1);
  });

  it("renders the LLM brain values (provider, base URL, model, api key status)", () => {
    render(<GeneralTab settings={TEST_SETTINGS} />);
    // `minimax` appears in multiple places (label hint + value).
    expect(screen.getAllByText(/minimax/i).length).toBeGreaterThanOrEqual(1);
    // `MiniMax-Text-01` is both default_model and fallback_model,
    // so it appears twice in the rendered KV rows.
    expect(screen.getAllByText(/MiniMax-Text-01/).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/✓ configured/i)).toBeInTheDocument();
  });

  it("renders the Server values (host, port)", () => {
    render(<GeneralTab settings={TEST_SETTINGS} />);
    expect(screen.getByText(/127\.0\.0\.1/)).toBeInTheDocument();
    expect(screen.getByText("8765")).toBeInTheDocument();
  });

  it("renders the User values (name)", () => {
    render(<GeneralTab settings={TEST_SETTINGS} />);
    expect(screen.getByText("Pilot")).toBeInTheDocument();
  });
});
