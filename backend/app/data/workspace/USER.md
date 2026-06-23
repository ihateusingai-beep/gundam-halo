# USER.md — About the Human

Learn about the person you're helping. Update this file as you
go. The runtime loads it into every turn's system prompt via
`app/core/agent_context.py`.

- **Name:** Ken
- **What to call them:** Ken
- **Pronouns:** he/him
- **Timezone:** Asia/Hong_Kong (UTC+8)
- **Notes:** _(free-form — anything you've learned)_

## Context

What do they care about? What projects are they working on? What
annoys them? What makes them laugh? Build this over time.

(Some starter hints the runtime learned from past sessions —
delete or expand as you go.)

- **Cares about:** Gundam (especially the Unicorn / NT-D line),
  Cantonese language preservation, Mac-first tooling, no-cloud
  privacy, single-user local AI agents over SaaS assistants
- **Active projects (as of 2026-06):**
  - `~/workspace/working/gundam-halo/` — this project, Gundam
    Halo, local voice + dashboard agent
  - `~/workspace/OpenJarvis/` — Mac control layer (forked)
  - `~/.openclaw/` — running OpenClaw instance
  - `~/workspace/vs code/sen-yue-read-score/` — Cantonese reading
    pronunciation scoring SPA
- **Annoyances:** cookie banners, sync-then-lose state,
  "agree to continue" walls, cloud-only tools that break offline
- **Humor:** dry, Cantonese tang ping (攤平) energy, references
  like "NT-D awakened" or "Unicorn mode on"

## Voice preferences

(Sprint 36 Tier 2 — populated by `~/.gundam-halo/skills/voice/
SKILL.md` and the runtime's `VoiceConfig`. Don't duplicate here;
reference it.)

- Preferred voice: `zh-HK-HiuMaanNeural` (default edge-tts)
- Wake phrases: see `VoiceConfig.wake_phrases` in
  `app/core/config.py`
- Strict mode: on (Sprint 17a default)

---

The more you know, the better you can help. But remember — you're
learning about a person, not building a dossier. Respect the
difference.