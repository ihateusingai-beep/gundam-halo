# HEARTBEAT.md — Periodic Checks

Keep this file empty (or with only comments) to skip heartbeat
API calls.

Add tasks below when you want the agent to check something
periodically.

## Example tasks

(Sprint 36+ — not yet wired. Reserved for the heartbeat
implementation.)

```markdown
- Check that `~/.gundam-halo/models/silero_vad.onnx` exists and
  is non-empty. Warn if missing.
- Verify `~/.gundam-halo/.venv` has the `whisper_hf` extras
  installed (look for `transformers/` importable).
- Tail the last 5 lines of `~/.gundam-halo/logs/audit.log` for
  any `mac_op_blocked` or `security_block` events.
```