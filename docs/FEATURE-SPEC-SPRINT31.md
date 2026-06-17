# Feature Spec — Sprint 31: Re-prioritize Sprint 26 menu (held-out eval → Layer 2 v2 → launchd → mlx-whisper)

> **Status:** DRAFT — proposed Sprint 31 scope.
> **This is a SPEC-ONLY sprint.** No code is
> written. Sprint 31 captures the **re-prioritized
> ordering** of the 4 tracks from Sprint 26's
> v0.1.5+ menu and freezes the dependency-aware
> sequence so the user can pick the right track
> to implement next.
> **Predecessors:**
> - Sprint 26 (commit `9dc8761`) shipped the
>   v0.1.5+ post-land menu spec with 4 tracks
>   (Layer 2 v2 self-record, launchd supervisor,
>   held-out Cantonese eval, mlx-whisper). The
>   menu-sprint pattern in Sprint 26 §Appendix A
>   leaves the **order to the user**.
> - Sprint 27 (commit `4a7a83e`) shipped the
>   4 Mark-XL tools.
> - Sprint 28 (commit `973fe4b`) shipped
>   `ToolsConfig` + conditional tool registration
>   (spec).
> - Sprint 29 (commit `c989538`) shipped
>   `ToolsConfig` + conditional tool registration
>   (impl).
> - Sprint 30 (commit `8eb388e`) shipped
>   Mark-XL follow-ups (2-track menu).
> - **Pre-existing test fix** (commit `33443bb`)
>   restored 0-fail baseline for the full voice +
>   tool + core test suite.
> **Scope:** spec-only freeze. The 4 tracks'
> **content** is unchanged from Sprint 26 §4.1-4.4
> — this spec only freezes the **re-prioritized
> sequence** (A → B → C → D) and the
> **track-to-sprint map** (which Sprint 32+ will
> implement which track). Total: ~3-5 days wall
> clock when implemented (same as Sprint 26 §5),
> spread across Sprint 32+ in dependency-aware
> order.
> **Out of scope (deferred to 33+):** runtime
> toggling of `enabled` (already deferred per
> Sprint 28 §4.5), per-tool API keys for non-
> flight tools, pre-Sprint 27 tool enable/disable,
> dashboard UI, hot-reload, mlx-whisper large-v3
> experiments.

---

## 0. Why this sprint exists

Sprint 26 shipped a **menu** of 4 post-v0.1.4
tracks, with the explicit caveat that the user
picks the order based on priority. The order
matters because:

- **Track 26-A (held-out Cantonese eval) is
  a *gate* for Track 26-B (Layer 2 v2
  self-record).** Track 26-B's success
  criterion is "WER < 10% on a personalised
  model" (per Sprint 26 §4.1 acceptance
  criterion). Without Track 26-A running
  first to measure the **baseline** (the
  v0.1.4 model WER on the user's actual
  voice), the user has no way to know if
  Track 26-B's fine-tune actually improved
  WER or just shifted the failure modes.
  Running Track 26-B without Track 26-A
  would force the user to fall back to
  the synthesised M9-C fixture, which
  Sprint 26 §0 calls out as inadequate
  ("the v0.1.4 acceptance test is a
  synthesised Cantonese fixture — a
  held-out test (user-recorded, ~30s) is
  needed to verify the fine-tune works
  on the user's actual voice").
- **Track 26-C (launchd supervisor) is
  *independent*** — it does not gate or
  block any other track, and does not
  depend on any model state. It is a
  quality-of-life improvement that can
  ship at any time.
- **Track 26-D (mlx-whisper) is
  *experimental*** — Sprint 26 §Appendix B
  already documents the language-hint gap
  as a High likelihood / High impact
  risk. mlx-whisper does not currently
  expose a `language = "cantonese"` hint
  the way the HF `pipeline` does. The
  user has been advised that this track
  may not ship at all.

The user has now (2026-06-18) picked the
**dependency-aware ordering**: held-out
eval first (gate) → Layer 2 v2 (gated)
→ launchd (independent) → mlx-whisper
(experimental). Sprint 31 is the **freeze**
of that ordering plus the **track-to-sprint
map** (which Sprint 32+ will implement
which track).

Sprint 31 is a **scope freeze, not a
content edit**. The 4 tracks' code
changes, file-by-file change set, risk
register, and acceptance tests are all
unchanged from Sprint 26 §4-7. This spec
adds:

1. **§1 Reordered priority** — Track 26-A
   (held-out eval) ships **before** Track
   26-B (Layer 2 v2).
2. **§2 Track-to-sprint map** — the
   user's preferred impl sequence
   (Sprint 32 = Track 26-A, Sprint 33 =
   Track 26-B, Sprint 34 = Track 26-C,
   Sprint 35 = Track 26-D, optional).
3. **§3 Dependency graph** — explicit
   diagram of which tracks gate which.
4. **§4 Risk register delta** — the
   *new* risks introduced by the
   reorder (e.g. "Track 26-A is
   skipped, Track 26-B's WER < 10%
   criterion has no baseline to
   compare against").
5. **§5 Acceptance tests** — the gate
   test the user must pass to unblock
   Track 26-B.
6. **§6 Sprint chain context** —
   where Sprint 31 sits in the v0.1.4
   → v0.1.5+ roadmap.

**No code is written in this sprint.**
Sprint 31 is spec-only. The CHANGELOG
entry is "Sprint 31 — Re-prioritized
v0.1.5+ menu (held-out eval → Layer 2 v2
→ launchd → mlx-whisper) — spec only".

## 1. Reordered priority

The user-confirmed ordering for the 4
Sprint 26 tracks is:

| Priority | Track | Sprint 26 ID | Sprint 31 ID | Wall clock | Depends on | Blocks |
|---|---|---|---|---|---|---|
| **1** | **Held-out Cantonese eval** | Track 26-3 (Sprint 26 §4.3) | **Track 31-A** | 1 day | (none — independent) | Track 31-B (gate) |
| **2** | **Layer 2 v2 self-record corpus** | Track 26-1 (Sprint 26 §4.1) | **Track 31-B** | 1-2 days | Track 31-A (gate) | (none — terminal) |
| **3** | **launchd supervisor** | Track 26-2 (Sprint 26 §4.2) | **Track 31-C** | 0.5 day | (none — independent) | (none — terminal) |
| **4** | **mlx-whisper inference accelerator** | Track 26-4 (Sprint 26 §4.4) | **Track 31-D** | 1-2 days | (none — independent) | (none — may not ship) |

**Total**: 3.5-5.5 days wall clock when
implemented, spread across Sprint 32-35
(4 sprints).

**Why this order**:

- **Track 31-A (held-out eval) is the
  gate for Track 31-B (Layer 2 v2)**.
  The user must record 30s of Cantonese
  + measure WER on the v0.1.4 model
  *before* investing 30 min of self-
  record corpus + 1 hour of personalised
  training. Without this baseline, the
  "WER < 10% on personalised model"
  criterion is meaningless — the user
  wouldn't know if the personalised
  model is actually better than the
  v0.1.4 baseline.
- **Track 31-C (launchd) is a quick win**
  — 0.5 day, completely independent of
  the model stack. The user can ship it
  at any time as a quality-of-life
  improvement.
- **Track 31-D (mlx-whisper) is
  experimental** — Sprint 26 §Appendix B
  already documents the language-hint
  gap. The user ships it last (or
  skips it) because the trade-off
  (300ms per-turn latency for ~50%
  energy cost) may not be worth the
  Cantonese quality regression.

**Sprint 26 §5 originally suggested a
similar ordering** ("Track 3 (held-out
eval) first, because it's a 1-day
sprint that gives the user the baseline
WER measurement before they invest in
Track 1"). Sprint 31 **confirms** that
suggestion and extends it to include
the track-to-sprint map.

## 2. Track-to-sprint map (Sprint 32+)

The user's preferred impl sequence is:

| Sprint | Track | Title | Wall clock | Notes |
|---|---|---|---|---|
| **Sprint 32** | Track 31-A | Held-out Cantonese eval impl | 1 day | Implements Sprint 26 §4.3 — `scripts/record-held-out.sh` + `tests/voice/test_held_out_eval.py` |
| **Sprint 33** | Track 31-B | Layer 2 v2 self-record corpus impl | 1-2 days | Implements Sprint 26 §4.1 — Tauri Record / Train / Swap cards + self-record manifest. **Gated by Sprint 32** — user must record 30s held-out + measure baseline WER first. |
| **Sprint 34** | Track 31-C | launchd supervisor impl | 0.5 day | Implements Sprint 26 §4.2 — `.plist` + `install-launchd.sh` + `lockfile.py`. Independent. |
| **Sprint 35** (optional) | Track 31-D | mlx-whisper inference accelerator impl | 1-2 days | Implements Sprint 26 §4.4 — `inference_backend = "mlx"` field + `_invoke_pipeline_mlx` method. May be skipped if mlx-whisper's language-hint gap is a blocker. |

**Sprint 32-35 are the **impl** sprints** —
each one ships a working feature. Sprint 31
is the **scope-freeze** sprint. Sprint 26 is
the **content-freeze** sprint (4 tracks'
code changes, file-by-file change set, risk
register, acceptance tests).

The user can pick a different impl sequence
(e.g. ship Track 31-C first because they
care about supervisor more than personal-
isation). The **only constraint** is:
**Track 31-B cannot ship before Track 31-A**
(gate relationship). Everything else is
parallel.

## 3. Dependency graph

```
                    Track 31-A (held-out eval)
                          |
                          | (gate: user records 30s + measures baseline WER)
                          v
                    Track 31-B (Layer 2 v2 self-record)
                          |
                          | (success: WER < 10% on personalised model)
                          v
                         (terminal — user has personalised model)


        Track 31-C (launchd supervisor)        Track 31-D (mlx-whisper)
              |                                          |
              | (independent)                             | (independent, experimental)
              v                                          v
             (terminal)                                  (may not ship)
```

**Key properties**:

- **Track 31-A → Track 31-B**: hard gate.
  Track 31-B's success criterion (WER
  < 10%) requires Track 31-A's baseline
  measurement for context. Without the
  baseline, the user cannot tell if
  Track 31-B improved WER or just
  shifted the failure modes.
- **Track 31-C, Track 31-D**: independent.
  No gates, no blocks. Can ship in any
  order relative to Track 31-A and 31-B.
- **Track 31-D**: optional. The user can
  skip it if the mlx-whisper Cantonese
  regression is unacceptable.

**Implication for Sprint 32-35 impl
sequence**: the user can ship Track 31-C
between Track 31-A and Track 31-B (e.g.
Sprint 33 = Track 31-C, Sprint 34 = Track
31-B) if they prefer the supervisor
improvement before the personalised
training. The only hard constraint is
**Track 31-A before Track 31-B**.

## 4. Risk register delta

The Sprint 26 §6 risk register is
**unchanged** — the 4 tracks' inherent
risks are not modified by the reorder.
This section adds **new risks** that
arise from the **reorder itself**:

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Track 31-A is skipped, Track 31-B ships without baseline** | Medium | High | Sprint 31 §5 (acceptance test 1) explicitly checks that the held-out WAV exists + baseline WER is measured before Track 31-B lands. The user is reminded in the Sprint 32 spec's "Predecessors" section. |
| **Track 31-A baseline WER is already < 10%, Track 31-B is wasted effort** | Low | Medium | The user can confirm the v0.1.4 model is "good enough" for their voice and skip Track 31-B entirely. Sprint 26 §4.3 acceptance criterion 2 ("if the user has Track 1 active, WER < 10%") explicitly checks for the personalised model. |
| **Track 31-C lock file conflicts with manual dev mode** | Medium | Medium | Sprint 26 §6 row 3 already documents this risk (lock file at `~/.gundam-halo/.backend.lock`). The lock is acquired at `create_app()` lifespan startup. The user can `launchctl unload` to disable the daemon before running `./run.sh` for dev. |
| **Track 31-D mlx-whisper doesn't support Cantonese language hint** | High | High | Sprint 26 §6 row 6 already documents this risk. The mlx-whisper path is **optional**; the user can `git revert <hash>` to fall back to the HF pipeline. The `voice-hf-mlx` extra is opt-in (`uv sync --extra voice-hf-mlx`). |
| **Track 31-B personalised fine-tune overfits to recording conditions** | Medium | Medium | Sprint 26 §6 row 2 already documents this risk. The held-out test (Track 31-A) is recorded in different conditions (different mic, different room) to catch overfit. If the held-out test fails after Track 31-B, the user re-trains with more Common Voice yue in the mix (70/30 Common Voice / self-record). |
| **The 4 tracks take longer than 4 sprints** | Medium | Medium | The user can ship Track 31-C in parallel with Track 31-B's training (the supervisor and the personalised model are independent). Track 31-D can be deferred indefinitely. |
| **Sprint 32-35 impl sprints drift back to "Sprint 27" naming convention** | Low | Low | The Sprint 31 spec uses "Sprint 32-35" for the impl sprints. The next spec (Sprint 32) will use the same numbering. The CHANGELOG entries are dated (2026-06-XX) so the numbering is just a label. |

## 5. Acceptance tests

The Sprint 31 spec-only freeze has its
own acceptance tests (the 4 impl sprints
each have their own acceptance tests per
Sprint 26 §7):

1. **Sprint 31 — the 4 tracks' content
   is unchanged from Sprint 26 §4-7** —
   `git diff docs/FEATURE-SPEC-SPRINT26.md
   docs/FEATURE-SPEC-SPRINT31.md` shows
   that Sprint 31 does NOT modify any
   code change, file-by-file change
   set, risk register, or acceptance
   test from Sprint 26. Sprint 31
   only **adds** §1-6 (the reorder +
   track-to-sprint map + dependency
   graph + new risks + acceptance
   tests for the spec-only freeze).
2. **Sprint 31 — the track-to-sprint
   map is explicit** — §2 names
   Sprint 32-35 as the impl sprints,
   with one track per sprint and
   the gate relationship (Track 31-A
   before Track 31-B) clearly stated.
3. **Sprint 31 — the user confirms
   the ordering** — the user signs
   off on Sprint 31 §1's priority
   table (Track 31-A → B → C → D)
   before Sprint 32 starts. The
   sign-off is recorded in `docs/
   tickets/M9-E.md` line 240-245
   (the M9-E Layer 2 v2 status
   section).
4. **Sprint 32 (Track 31-A) —
   the held-out WAV + baseline
   WER are measured** — the user
   runs `bash scripts/record-held-out.sh`
   once (5 min) + `pytest tests/voice/
   test_held_out_eval.py -v`. The
   test records the baseline WER
   (e.g. "WER = 18% on the v0.1.4
   model") in the Sprint 32 spec's
   "Acceptance tests" section. This
   is the **gate** for Sprint 33.
5. **Sprint 33 (Track 31-B) —
   the personalised WER is < 10%** —
   the user activates the personalised
   model + runs the same held-out test.
   The test records "WER = 8% on the
   personalised model" (vs. 18% on
   v0.1.4) in the Sprint 33 spec's
   "Acceptance tests" section. If
   WER ≥ 10%, the user can either
   record more self-record data (30
   min → 60 min) or re-train with
   more Common Voice yue in the mix
   (70/30 vs. 50/50).

## 6. Sprint chain context

| Sprint | Commit | Status | Description |
|---|---|---|---|
| 16 | `4e61b8f`, `b6e1989` | shipped | 4 new tools + wake phrase + VoiceTab |
| 17a | `12ea7c7`, `4db7d43` | shipped | strict wake-phrase mode + `SanitizerState` cross-sentence `<think>` fix + 12 tracks |
| 17b | `00308c6` → `4d925ab` | shipped | Track A-F model infra, YuesubASR, OpenCC+BERT, dual VAD, use-mic-analyser, Settings switcher |
| 18 | `33aafaa` | shipped | CyberWaveform mounted in CockpitLayout via SignalCard + ASR engine + corrector radio + Restart banner |
| 19a | `f8bbfa4` | shipped | `fsmn_vad.py` lazy-load + SNR-based level mapping |
| 19b | `69957b2` | shipped | `app/core/restart.py` `schedule_restart` via `os.execvp` |
| 19c P1 | `756bee6` | shipped | voice_websocket VAD event subscription + `always_on_mic` field |
| 19c P2 | `de87c1b` | shipped | `use-vad-state-autofire.ts` + always-on mic UI toggle |
| 19d prep | `0388699` | shipped | 4 smoke tests for finetune script |
| 19d addendum | `a8d8e17` | shipped | background monitor with 5 exit codes + `os.waitpid(pid, WNOHANG)` |
| 20 | `ffc2624` | shipped | 4-step v0.1.4 rollout plan (spec-only) |
| 21 | `3353106` | shipped | `prepare_common_voice_yue` impl — split_by_client_id, cap_at_hours, save_splits_as_parquet |
| 22 | `e0b87f9` | shipped | v0.1.4 land plan spec-only (4 tracks) |
| 23 | `4e85e99` | shipped | v0.1.4 land impl Tracks 1+2+4 — `WhisperHFASR` backend + warning removal + banner removal |
| 24 | `c24eb85` | shipped | v0.1.4 finalization Track 3 acceptance gate spec-only |
| 25 | `1461ce8` | shipped | v0.1.4 finalization Track 3 impl template spec-only |
| 26 | `9dc8761` | shipped | v0.1.5+ post-land menu spec-only (4 tracks) |
| 27 | `aba7eb6` (spec), `4a7a83e` (impl) | shipped | Mark-XL tool import 4 tools (web_search / youtube_summarize / flight_finder / send_message) |
| 28 | `973fe4b` | shipped | `ToolsConfig` + conditional tool registration (spec) |
| 29 | `c989538` | shipped | `ToolsConfig` + conditional tool registration (impl) |
| 30 | `8eb388e` | shipped | Mark-XL follow-ups spec-only (2 tracks) |
| Pre-existing fix | `33443bb` | shipped | test_default_config base_url assertion fix |
| **31 (this sprint)** | TBD | **DRAFT** | **Re-prioritize Sprint 26 menu: held-out eval → Layer 2 v2 → launchd → mlx-whisper (spec-only)** |
| 32 (planned) | TBD | not started | Track 31-A impl — Held-out Cantonese eval (1 day) |
| 33 (planned) | TBD | not started | Track 31-B impl — Layer 2 v2 self-record corpus (1-2 days, gated by Sprint 32) |
| 34 (planned) | TBD | not started | Track 31-C impl — launchd supervisor (0.5 day) |
| 35 (planned, optional) | TBD | not started | Track 31-D impl — mlx-whisper inference accelerator (1-2 days, may not ship) |

**v0.1.4 status**: tagged in main. The
Sprint 25 commit (Track 3 deletion)
shipped. The M9-C augmented system note
workaround is deleted. The user is
running the v0.1.4 model in production.

**v0.1.5+ status**: spec-only freeze
across Sprint 26 (content) + Sprint 30
(Mark-XL follow-ups) + Sprint 31 (this
sprint — reorder). No code has been
written for v0.1.5+ features yet.

**Sprint 32+ is the first impl sprint
for v0.1.5+** (Track 31-A held-out
eval). The user can also pick Mark-XL
follow-ups (Sprint 30 Track A send_message
real pyautogui or Track B flight_finder
real extractor) for Sprint 32 instead —
the Sprint 30 tracks are **independent**
of the Sprint 31 tracks.

**Strategic context**: the v0.1.4 land
established the production-grade Cantonese
baseline (WER < 20% on Common Voice yue).
The v0.1.5+ menu is about **personalisation
+ availability + speed** on top of that
baseline. The reorder captures the user's
priorities: **personalisation first**
(held-out eval → Layer 2 v2), then
**availability** (launchd), then
**speed** (mlx-whisper, experimental).

## 7. File-by-file change set (when Sprint 32+ lands)

This spec-only freeze does NOT add any
code changes. The 4 tracks' file-by-file
change sets are unchanged from Sprint 26 §5:

| Path | Change | LoC est. | Sprint 31 ID |
|---|---|---|---|
| `scripts/record-held-out.sh` | NEW — interactive 5-min record + transcribe | +80 / 0 | Track 31-A |
| `backend/tests/voice/test_held_out_eval.py` | NEW — 3-4 held-out eval tests | +100 / 0 | Track 31-A |
| `frontend/src/routes/settings/VoiceTab.tsx` | New "Personalised Fine-tune" section (3 cards) | +200 / 0 | Track 31-B |
| `frontend/src-tauri/src/commands.rs` | New IPC commands (start_record, stop_record, start_train, etc.) | +150 / 0 | Track 31-B |
| `frontend/src-tauri/src/recording.rs` | NEW — record + transcribe parallel pipeline | +200 / 0 | Track 31-B |
| `backend/scripts/finetune_whisper_yue.py` | Document `--base_model_path` and `--train_audio_dir` flags (no new code) | +30 / 0 | Track 31-B |
| `backend/tests/voice/test_finetune_script.py` | Add 1 test for `--base_model_path` flag | +30 / 0 | Track 31-B |
| `backend/tests/voice/test_self_record_manifest.py` | NEW — 5-8 tests for self-record manifest | +150 / 0 | Track 31-B |
| `scripts/install-launchd.sh` | NEW — copy `.plist` + `launchctl load` | +50 / 0 | Track 31-C |
| `scripts/com.gundam.halo.plist` | NEW — launchd configuration XML | +30 / 0 | Track 31-C |
| `scripts/uninstall-launchd.sh` | NEW — `launchctl unload` + rm | +20 / 0 | Track 31-C |
| `backend/app/core/lockfile.py` | NEW — lock file acquire / release / conflict | +80 / 0 | Track 31-C |
| `backend/app/main.py` | Wire lock file into `create_app()` lifespan | +10 / 0 | Track 31-C |
| `backend/tests/test_launchd_plist.py` | NEW — 3-5 lint tests | +100 / 0 | Track 31-C |
| `backend/tests/core/test_lockfile.py` | NEW — 4-6 lock file tests | +120 / 0 | Track 31-C |
| `backend/app/voice/asr/whisper_hf.py` | Add `inference_backend: str = "hf"` field + `_invoke_pipeline_mlx` method | +80 / 0 | Track 31-D |
| `backend/app/voice/asr/asr_factory.py` | Forward `device = "mlx"` to `inference_backend = "mlx"` | +20 / 0 | Track 31-D |
| `backend/pyproject.toml` | New `voice-hf-mlx` optional extra | +5 / 0 | Track 31-D |
| `backend/tests/voice/test_whisper_hf.py` | Add 3-4 tests for `inference_backend = "mlx"` (mocked) | +100 / 0 | Track 31-D |
| `docs/CHANGELOG.md` | v0.1.5 release entry per track | +120 / 0 | (each Sprint 32-35) |
| `docs/tickets/M9-E.md` | Update Layer 2 v2 status when Track 31-B lands | +10 / 0 | (Sprint 33) |

**Total**: ~1,485 LoC across 18 files.
~3.5-5.5 days wall clock when implemented,
spread across Sprint 32-35 (4 sprints).

## 8. Sign-off

Sign-off requires:

1. **User confirms the re-prioritized
   ordering** (Track 31-A → B → C → D).
2. **User confirms the track-to-sprint
   map** (Sprint 32-35).
3. **User confirms the gate relationship**
   (Track 31-A before Track 31-B).
4. **User confirms Track 31-D is optional**
   (may not ship if mlx-whisper Cantonese
   regression is unacceptable).

Once signed off, Sprint 32 starts with
the held-out Cantonese eval impl.

---

## Appendix A — Why Sprint 31, not just a re-prioritized table in Sprint 26

Sprint 26's spec-only freeze has a
"§5 File-by-file change set" with a
recommended impl sequence (Track 3
first, then Track 1, then Track 2,
then Track 4). The user could have
just confirmed that sequence in a
chat message and moved on. Why a
dedicated Sprint 31 spec?

- **Sprint 26's recommended sequence is
  a "most likely" guess** — the user
  might want a different order based
  on their priorities. Sprint 31
  captures the **confirmed** order
  with explicit sign-off.
- **Sprint 26's recommended sequence
  does not name the impl sprints**
  (Sprint 27, 28, 29, 30). Sprint 31
  names **Sprint 32-35** as the impl
  sprints so the next spec (Sprint 32)
  has a clear predecessor.
- **Sprint 26's recommended sequence
  does not include the gate test** —
  Sprint 31 §5 acceptance test 4
  explicitly defines the gate
  (the user must record 30s held-out
  + measure baseline WER before Sprint
  33 can start).
- **Sprint 26 does not capture the
  reorder risk register** — Sprint 31
  §4 documents the **new** risks
  introduced by the reorder itself
  (e.g. "Track 31-A is skipped,
  Track 31-B ships without baseline").

In short: Sprint 26 is **content**,
Sprint 31 is **commitment**. Sprint 31
turns "you might want to ship held-out
eval first" into "Sprint 32 will ship
held-out eval, gated by §5 acceptance
test 4".

## Appendix B — Why mlx-whisper is last (and may not ship)

Sprint 26 §Appendix B already documents
the language-hint gap as the primary
risk. The user has chosen to ship it
last in the Sprint 31 ordering because:

- **mlx-whisper is a drop-in inference
  accelerator** — the training still
  uses HF + LoRA per Sprint 19d. The
  user already has a working v0.1.4
  pipeline. mlx-whisper is a "nice to
  have" latency improvement, not a
  blocking feature.
- **Cantonese language hint is critical** —
  per Sprint 26 §Appendix B, the HF
  pipeline accepts `language = "cantonese"`
  via `generate_kwargs`. mlx-whisper
  does not currently expose this hint
  the same way. The WER regression on
  Cantonese is High likelihood / High
  impact.
- **The user can `git revert` Track 31-D**
  — the change is small (~100 LoC
  across 4 files). If the WER
  regression is unacceptable, the
  user reverts and stays on the HF
  pipeline. The mlx-whisper path
  is opt-in (`uv sync --extra voice-hf-mlx`).
- **The energy cost saving (~50%) is
  marginal on M-series MacBook Pro** —
  the v0.1.4 model is small enough
  that the HF pipeline already runs
  under 1W on M-series. The 50% saving
  is ~0.5W, which is within thermal
  headroom.

The user can skip Track 31-D entirely
if the WER regression is a blocker.
Sprint 35 is **optional**.

## Appendix C — Test count evolution (cumulative)

| Sprint | Test count (delta) | Test count (cumulative) |
|---|---|---|
| 16 | +50 | 50 |
| 17a | +30 | 80 |
| 17b | +80 | 160 |
| 18 | +10 | 170 |
| 19a | +20 | 190 |
| 19b | +10 | 200 |
| 19c P1 | +5 | 205 |
| 19c P2 | +5 | 210 |
| 19d prep | +4 | 214 |
| 19d addendum | +7 | 221 |
| 20 | (spec-only) | 221 |
| 21 | +5 | 226 |
| 22 | (spec-only) | 226 |
| 23 | +38 | 264 |
| 24 | (spec-only) | 264 |
| 25 | (spec-only) | 264 |
| 26 | (spec-only) | 264 |
| 27 | +93 | 357 |
| 28 | (spec-only) | 357 |
| 29 | +27 | 384 |
| 30 | (spec-only) | 384 |
| Pre-existing fix | (no new tests) | 384 |
| **31** | **(spec-only)** | **384** |
| 32 (Track 31-A) | +3-4 | 387-388 |
| 33 (Track 31-B) | +6-9 | 393-397 |
| 34 (Track 31-C) | +7-11 | 400-408 |
| 35 (Track 31-D) | +3-4 | 403-412 |

**Cumulative test count after Sprint 32
(Track 31-A)**: 387-388 tests, 0 fail.
**Cumulative test count after Sprint 35
(all 4 tracks)**: 403-412 tests, 0 fail.

## Appendix D — Sprint chain context

Sprint 26 §Appendix G already documents
the sprint chain context. Sprint 31
extends it with the v0.1.5+ impl
sprints (Sprint 32-35).

**v0.1.4 land** (Sprint 22-25) shipped
the production-grade Cantonese baseline.
**v0.1.4 finalization** (Sprint 24-25)
shipped the M9-C augmented system note
deletion. The M9-E ticket is **closed
for v0.1.4** but **open for v0.1.5+**
(Layer 2 v2 self-record corpus).

**Sprint 26** opened the v0.1.5+ menu
with 4 tracks. **Sprint 30** added 2
more tracks (Mark-XL follow-ups). **Sprint
31** (this spec) reorders the 4 Sprint 26
tracks into a dependency-aware sequence
and freezes the track-to-sprint map.

**Sprint 32-35** are the impl sprints
for the 4 reordered tracks. The user
can interleave Sprint 30's Mark-XL
follow-ups (Track A send_message real
pyautogui, Track B flight_finder real
extractor) into the same sprints if
they prefer.

**Out of scope for Sprint 31-35**:
runtime toggling of `enabled` (deferred
to 36+ per Sprint 28 §4.5), per-tool
API keys for non-flight tools, pre-
Sprint 27 tool enable/disable, dashboard
UI, hot-reload, mlx-whisper large-v3
experiments.
