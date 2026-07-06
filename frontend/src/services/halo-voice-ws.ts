/**
 * Voice WebSocket service — back-compat shim to `services/voice/`.
 *
 * Sprint 56 R7: this file used to be a 532-LoC monolith. It is
 * now a 30-line shim that re-exports from the new
 * `services/voice/` subpackage. All previous imports continue
 * to work:
 *
 *   import { voiceBegin, voiceSendAudio, ... } from "@/services/halo-voice-ws"
 *   import type { VoiceState, VoiceWSEvent } from "@/services/halo-voice-ws"
 *
 * The actual implementation:
 *   - `services/voice/types`       — event + state type definitions
 *   - `services/voice/connection`  — `VoiceWsClient` class + state machine
 *   - `services/voice/api`         — public turn control + subscription API
 *
 * This shim will be removed in a future sprint once all callers
 * update to import from `@/services/voice` directly.
 */
export * from "./voice";
export { VoiceWsClient } from "./voice";
