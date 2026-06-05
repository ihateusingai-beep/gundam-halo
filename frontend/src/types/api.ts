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
