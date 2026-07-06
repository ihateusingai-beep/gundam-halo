/**
 * Voice WebSocket service — Sprint 56 R7 subpackage.
 *
 * Back-compat shim that re-exports every public symbol from
 * `services/halo-voice-ws.ts` (the pre-R7 532-LoC monolith).
 *
 * The actual modules:
 *   - `services/voice/types`       — 11 event + state type defs
 *   - `services/voice/connection`  — `VoiceWsClient` class +
 *                                     state machine + handleEvent
 *   - `services/voice/api`         — public turn control +
 *                                     subscription + console debug
 *
 * The old `services/halo-voice-ws.ts` becomes a 30-line shim
 * that re-exports from here.
 */
export * from "./types";
export * from "./api";
export { VoiceWsClient } from "./connection";
