/**
 * TypeScript types matching the Gundam Halo backend API.
 * (See /Users/kencheng/workspace/working/gundam-halo/backend/app/api/*.py)
 */

export interface HealthResponse {
  status: string;
  version: string;
  name: string;
}

export interface Gauges {
  cpu_percent: number;
  memory_percent: number;
  disk_percent: number;
  network_sent_mb: number;
  network_recv_mb: number;
}

export interface ProjectSummary {
  name: string;
  status: "active" | "paused" | "archived";
  created_at: string;
  agent_type: string;
  message_count: number;
  session_count: number;
  last_activity_at: string;
}

export interface ProjectCreate {
  name: string;
  description?: string;
  agent_type?: string;
}

export interface SessionInfo {
  id: string;
  project_name: string;
  agent_type: string;
  started_at: string;
  message_count: number;
}

export interface SessionStart {
  project_name: string;
  agent_type?: string;
}

export interface MessageSend {
  content: string;
}

export interface ShellRequest {
  command: string;
  timeout_sec?: number;
}

export interface ShellResponse {
  command: string;
  exit_code: number;
  stdout: string;
  stderr: string;
  duration_ms: number;
}

export interface FileReadRequest {
  path: string;
}

export interface FileReadResponse {
  path: string;
  content: string;
  bytes: number;
}

export interface FileWriteRequest {
  path: string;
  content: string;
}

export interface FileWriteResponse {
  path: string;
  bytes: number;
  status: string;
}

export interface MessageResponse {
  session_id: string;
  user_message: string;
  agent_response: string;
  tool_calls_made: number;
  success: boolean;
  error?: string;
}

export interface SessionListItem {
  id: string;
  agent_type: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

/** A5 — wire shape of a single message in the session history. */
export interface SessionHistoryMessage {
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  tool_calls: Array<{ id: string; name: string; arguments: Record<string, any> }>;
  tool_call_id?: string;
  name?: string;
}

/** A5 — response from GET /api/sessions/:id/messages */
export interface SessionHistoryResponse {
  session_id: string;
  project_name: string | null;
  message_count: number;
  messages: SessionHistoryMessage[];
}

export interface SessionMessagesResponse {
  session_id: string;
  project_name: string;
  message_count: number;
  messages: Array<{
    role: "system" | "user" | "assistant" | "tool";
    content: string;
    tool_calls: Array<{ id: string; name: string; arguments: Record<string, any> }>;
    tool_call_id?: string;
    name?: string;
  }>;
}

// Theme
export type GundamTheme =
  | "gundam-ntd"
  | "gundam-seed"
  | "gundam-crossbone"
  | "gundam-ntd-green"
  | "gundam-00"
  | "gundam-destiny"
  | "gundam-god"
  | "gundam-cartoon"
  | null;

export interface ThemeInfo {
  id: GundamTheme;
  name: string;
  emoji: string;
  description: string;
}

// Settings
export interface SettingsMac {
  default_path_policy: string;
  file_read_paths: string[];
  file_write_paths: string[];
  shell_allowlist: string[];
  a11y_enabled: boolean;
  apple_script_enabled: boolean;
  notifications_enabled: boolean;
}

export interface SettingsLLM {
  provider: string;
  base_url: string;
  default_model: string;
  fallback_model: string;
  api_key_configured: boolean;
}

export interface SettingsTelegram {
  enabled: boolean;
  allowed_chat_ids: number[];
  command_prefix: string;
  bot_token_configured: boolean;
}

export interface SettingsSecurity {
  audit_log: string;
  audit_max_size_mb: number;
  injection_scan: boolean;
  require_confirm_for: string[];
}

export interface SettingsServer {
  host: string;
  port: number;
  log_level: string;
  require_tailscale: boolean;
  tailscale_hostname: string;
}

export interface SettingsUser {
  name: string;
  default_theme: string;
}

export interface SettingsApp {
  version: string;
  home: string;
  config_path: string;
}

export interface Settings {
  app: SettingsApp;
  user: SettingsUser;
  llm: SettingsLLM;
  server: SettingsServer;
  mac: SettingsMac;
  telegram: SettingsTelegram;
  security: SettingsSecurity;
}

// M7-Phase-2: user memory API types
export interface MemoryEntry {
  key: string;
  value: string;
  updated_at: number;
  created_at: number;
}

export interface MemoryUserList {
  users: string[];
}

export interface MemoryUserEntries {
  user: string;
  entries: MemoryEntry[];
}

export interface AuditEntry {
  id: string;
  ts: string;
  event_type: string;
  data: Record<string, any>;
}

// Sprint 39 — held-out eval row (matches the backend
// `load_eval_history()` return shape; one row per CLI run).
// `wer_pct` is rounded to 2 dp at the backend.
export interface EvalRunRow {
  timestamp: string;
  timestamp_ms: number;
  wer_pct: number;
  passed: boolean;
  wav_path: string;
  asr_backend: string;
  duration_sec: number;
  source_path: string;
}

// Sprint 39 — setup wizard state for the SetupWizard card.
export interface SetupState {
  status: string;          // "in_progress" | "complete" | "skipped" | "pending"
  current_step: number;    // 1..8
  completed_steps: number[];
  started_at: string | null;
  finished_at: string | null;
  skipped: boolean;
  reason: string | null;
}
