# Sprint 59 — Per-theme gundam assets follow-up

> **Status**: In progress · 2026-07-09
> **Comes after**: Sprint 58 (`6982dbc` + `cf95e41`)
> **Goal**: Close the P4 deferred item from Sprint 58 — every theme
> ships with a full 9-emotion avatar set + per-theme hero bg.

---

## 1. Why this sprint exists

Sprint 58 Phase 4 wire-up (`6982dbc`) fixed the broken-bg CSS bug,
consolidated the 9-theme union, and added a single source of truth
(`lib/theme-bg-constants.ts` + `lib/avatar-paths.ts`) so the per-theme
asset URLs are pinned and cascade correctly.

Sprint 58 Phase 1-3 (`cf95e41`) shipped 76 gundam assets — but only
**5 of 9 themes have a full 9-emotion set**:

| Theme         | Anchor | Emotion set status               |
| ------------- | :----: | -------------------------------- |
| ntd (legacy)  |   —    | 9 (uses bare `emotions/`)        |
| seed          |   —    | 9 (Sprint 57)                    |
| ntd-green     |   ✓    | 9 (Sprint 58 Phase 3B)           |
| 00            |   ✓    | 9 (Sprint 58 Phase 3B)           |
| destiny       |   ✓    | 9 (Sprint 58 Phase 3B)           |
| god           |   ✓    | 9 (Sprint 58 Phase 3B)           |
| crossbone     |   ✗    | **3 partial** (confused/sad/warning) |
| halo          |   ✗    | **0**                            |
| cartoon       |   ✗    | **0**                            |

The avatar PNGs for these 3 themes either fall back to the NT-D
baseline (`emotions/`) or fail entirely with broken-image icons
when the user picks crossbone / halo / cartoon. HALO and CARTOON
also lack emotion-set entries in `THEMES_WITH_AVATAR_SET` (Sprint
58 audit P1 found this asymmetry and documented it in
`avatar-paths.ts`).

---

## 2. Scope

### 2.1 What ships

**Phase A — Fresh anchor portraits** (3 new PNGs, ~2 MB total)

- `avatars/anchors/anchor-crossbone.png` (1024×1024, fresh, NOT i2i
  from existing 3 partial PNGs — anchor is the clean reference
  that drives 9 consistent emotion variants)
- `avatars/anchors/anchor-halo.png` (1024×1024, fresh)
- `avatars/anchors/anchor-cartoon.png` (1024×1024, fresh)

Each anchor is a character portrait, not an emotion shot — neutral
expression, cockpit-ready composition, NT-D Unicorn's framing
style (centered, ~60% of frame).

### 2.2 Phase B — Full emotion sets via i2i** (27 new PNGs, ~16 MB total)

For each of the 3 new anchors, generate 9 emotion variants via
`matrix_generate_image` with `input_files` = local anchor path.
Same prompt-delta strategy as Sprint 58 Phase 3B:

```
input_files: [/abs/path/to/anchor-{theme}.png]
prompt:      "{character desc}, {emotion pose desc}, anime portrait,
              centered composition, dark moody cockpit background,
              psychoframe cyan/pink rim lighting, ultra-detailed
              mechanical suit details, sharp focus, 1024x1024"
```

| Emotion   | Prompt suffix                                          |
| --------- | ------------------------------------------------------ |
| idle      | "neutral relaxed pose, slight smile, calm eyes"         |
| listening | "tilted head, attentive eyes, hand on ear-piece"        |
| thinking  | "hand on chin, contemplative gaze, slight frown"        |
| speaking  | "open mouth mid-speech, gesturing hand, confident"      |
| warning   | "raised fist, alarmed expression, urgent stance"        |
| damage    | "smoke on shoulder, cracked visor, fierce scowl"        |
| joy       | "bright wide smile, eyes closed in laughter, arms up"   |
| sad       | "downcast eyes, slumped shoulders, single tear"         |
| confused  | "head tilted, one eyebrow raised, mouth slightly open"  |

Crossbone uses the Crossbone Gundam X-1 patch (skull motif,
burgundy + gold). Halo uses the original Gundam Halo silhouette
(decidedly more abstract than NT-D). Cartoon uses the SD /
chibi Gundam style from the official 1990s merchandise.

### 2.3 Phase C — Wire-up**

- **Add HALO + CARTOON to `THEMES_WITH_AVATAR_SET`** in
  `lib/avatar-paths.ts` (currently missing per Sprint 58 audit P1)
- **CROSSBONE stays in the set** (already present since Sprint 58
  with 3 partial PNGs; full set lands in this sprint)
- **Delete the 3 legacy crossbone PNGs** (`confused.png`,
  `sad.png`, `warning.png`) — they were generated via the old
  text-to-image pipeline without an anchor and have an inconsistent
  character design (visible drift vs. the new anchor)
- **Update `avatar-paths.test.ts`** with 3 new it-blocks for
  crossbone full set, halo full set, cartoon full set
- **CHANGELOG + `__version__` 0.2.7 → 0.2.8** (MINOR — new themed
  asset)
- **Commit** in 2 separate commits (binary asset diff bloat
  mitigation, same as Sprint 58):
  - `xxxxx` Sprint 59 (in-session) — Per-theme assets Phase A+B
    (30 binary files, ~18 MB)
  - `xxxxx` Sprint 59 (in-session) — Per-theme wire-up: HALO +
    CARTOON in `THEMES_WITH_AVATAR_SET`, drop 3 legacy crossbone
    PNGs, tests, version bump 0.2.7→0.2.8

### 2.4 Out of scope (deferred)

- **Crossbone 4-variant bg set** (core-02/03/04): Phase 2.5 from
  Sprint 58, deferred. Sprint 59 only completes the core-01
  variant that already exists from Sprint 58.
- **Halo + Cartoon full 4-variant bg sets**: same as above.
- **Per-USER EQ independent of theme**: deferred since Sprint 57.
- **Live2D model license**: deferred indefinitely (license blocker).

---

## 3. Image gen cost / time estimate

`matrix_generate_image` typically takes:
- Anchor (text-to-image, no input_files): 30-60 s × 3 = 90-180 s
- Emotion variant (i2i, input_files = anchor): 15-25 s × 27 =
  405-675 s

Total: 8-15 min image gen + 10 min manual QA (3 themes × 9 PNGs
visual check) + 20 min wire-up + 10 min senior-engineer audit +
10 min commit + 5 min CHANGELOG = **~60 min end-to-end**.

Image gen cost estimate: matrix MCP usage runs on MiniMax billing.
Based on Sprint 58's actual usage (76 PNGs ≈ ~$0.40), the 30 new
PNGs should be ≈ $0.16.

---

## 4. Senior-engineer audit checklist (Sprint 56.6 standing rule)

Pre-commit, run the audit and address findings:

1. **Prompt-delta drift**: render all 27 new PNGs as a 9×3 grid
   (3 themes × 9 emotions) and check character consistency. Any
   cross-theme drift on the same emotion = bug.
2. **Aspect-ratio uniformity**: confirm every PNG is 1024×1024.
   `file <path>` on each. Any deviation = bug.
3. **Legacy crossbone PNGs deleted**: verify
   `avatars/emotions-crossbone/` contains exactly 9 PNGs (the
   3 legacy deleted, 6 new + 3 reproduced = 9), no leftovers.
4. **Path resolution test**: extend `avatar-paths.test.ts` to
   assert the per-theme URL for ALL 9 themes resolves to the
   on-disk directory.
5. **Theme-bg asymmetry**: confirm `THEMES_WITH_AVATAR_SET` has
   8 entries (was 6 in Sprint 58; + HALO + CARTOON), matching
   `THEMES_WITH_BG_SET`'s 8 entries (NT-D excluded from both for
   the same reason — NT-D uses the bare `emotions/` + Unicorn bg).

---

## 5. Standing rules (carry-over from Sprint 58)

- Every `themeId` field in app code is **always string-keyed**
  against the 9-theme union (`GundamTheme` from `types/api.ts`).
- Per-theme asset paths use `gundam-<slug>` strip + NT-D's bare
  `emotions/` + `bg-unicorn-core-XX.jpg` fallback. Don't introduce
  new bare names.
- Adding a new theme = add to both `THEMES_WITH_BG_SET` and
  `THEMES_WITH_AVATAR_SET` + drop asset files + add to StepTheme
  THEMES list. No other code changes required.
- Asset commits stay separate from wire-up commits (binary diff
  bloat mitigation).
- Image gen prompt must be materially different from the input
  for i2i (otherwise matrix returns input unchanged).

---

## 6. Commit plan

```
[main]
  cf95e41 Sprint 58 (in-session) — Per-theme gundam assets Phase 1-3 ...
  6982dbc Sprint 58 (in-session) — Per-theme gundam assets Phase 4 wire-up ...
  xxxxxx  Sprint 59 (in-session) — Per-theme assets Phase A+B: anchors + full emotion sets
          (crossbone + halo + cartoon, 30 binary files, ~18 MB)
  xxxxxx  Sprint 59 (in-session) — Per-theme wire-up: HALO + CARTOON in
          THEMES_WITH_AVATAR_SET, drop 3 legacy crossbone PNGs, tests,
          version bump 0.2.7→0.2.8
```

---

## 7. Definition of done

- [ ] 3 new anchors on disk (crossbone + halo + cartoon)
- [ ] 27 new emotion PNGs on disk (3 themes × 9 emotions)
- [ ] 3 legacy crossbone PNGs deleted from disk + commit
- [ ] `lib/avatar-paths.ts` `THEMES_WITH_AVATAR_SET` has 8 entries
      (was 6: + halo + cartoon)
- [ ] `lib/avatar-paths.test.ts` extended with 3 it-blocks
      (crossbone full, halo full, cartoon full)
- [ ] `lib/theme-bg-constants.test.ts` (or constants.test.ts)
      confirms crossbone / halo / cartoon bg URLs resolve
- [ ] 210+/210+ vitest pass + 0 new tsc errors
- [ ] CHANGELOG entry above Sprint 58
- [ ] `__version__` bumped 0.2.7 → 0.2.8 in all 4 surfaces
- [ ] Senior-engineer audit findings resolved (or explicitly
      documented as deferred)
- [ ] 2 separate commits (assets + wire-up)