/**
 * PersonalisedFineTuneSection — Sprint 33b Record / Train / Swap
 * cards.
 *
 * Extracted from VoiceTab.tsx (Sprint 56.7). This is the
 * largest single section (~180 LoC) — a 3-card flow per
 * FEATURE-SPEC-SPRINT26.md §4.1 + Appendix C that wires the
 * Record → Train → Swap user-driven Cantonese fine-tune
 * workflow.
 *
 * ## Architecture note
 *
 * `runFinetuneCommand` was extracted into a sibling module
 * (`tabs/voice/runFinetuneCommand.ts`). The function takes
 * the per-card `setPhase` / `setMessage` setters as a
 * parameter so each card's state slot is independently
 * updatable. The original code put this function inline in
 * VoiceTab's component body — extracting it makes the
 * dispatcher independently testable and lets this section
 * own its 3 phase machines without leaking refs to the
 * orchestrator.
 *
 * ## Sprint 33 scope decision (preserved from the original
 * docstring — read before refactoring)
 *
 * The three cards are wired to the Tauri IPC commands
 * defined in `frontend/src-tauri/src/commands.rs`
 * (`start_record`, `stop_record`, `start_train`,
 * `get_train_progress`, `activate_model`). The contracts
 * are pinned by the rustdoc comments on those commands — no
 * frontend-side changes are needed when the Rust pipeline
 * evolves.
 */
import { useState } from "react";

import { HudCard } from "@/components/gundam/HudCard";
import { isTauriRuntime } from "@/lib/tauri";

import { Section } from "../../../shared";

import { runFinetuneCommand } from "../runFinetuneCommand";
import type { CardPhase } from "../types";

export function PersonalisedFineTuneSection() {
  // Three independent phase + message slots, one per card.
  const [recordPhase, setRecordPhase] = useState<CardPhase>("idle");
  const [recordMessage, setRecordMessage] = useState<string>("");
  const [trainPhase, setTrainPhase] = useState<CardPhase>("idle");
  const [trainMessage, setTrainMessage] = useState<string>("");
  const [swapPhase, setSwapPhase] = useState<CardPhase>("idle");
  const [swapMessage, setSwapMessage] = useState<string>("");

  return (
    <Section title="Personalised Fine-tune (Sprint 33b)">
      <p
        className="text-xs text-[var(--text-secondary)] font-mono mb-2"
        data-testid="personalised-finetune-intro"
      >
        Personalise the v0.1.4 WhisperHFASR on your own voice.
        Three steps, run independently — you can pause between
        Record and Train. Each card calls a Tauri IPC command
        defined in <code>frontend/src-tauri/src/commands.rs</code>
        (the recording / training pipeline lives in
        <code> recording/</code>; Sprint 33b ships the real
        cpal + hound + parallel WhisperHFASR subprocess impl
        that Sprint 33 stubbed — see the Sprint 33b commit
        message for the scope decision).
      </p>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <RecordCard
          phase={recordPhase}
          message={recordMessage}
          onStart={() =>
            runFinetuneCommand("start_record", {
              setPhase: setRecordPhase,
              setMessage: setRecordMessage,
              label: "Record",
            })
          }
        />
        <TrainCard
          phase={trainPhase}
          message={trainMessage}
          onStart={() =>
            runFinetuneCommand("start_train", {
              setPhase: setTrainPhase,
              setMessage: setTrainMessage,
              label: "Train",
            })
          }
        />
        <SwapCard
          phase={swapPhase}
          message={swapMessage}
          onStart={() =>
            runFinetuneCommand("activate_model", {
              setPhase: setSwapPhase,
              setMessage: setSwapMessage,
              label: "Swap",
            })
          }
        />
      </div>
      <p className="text-[10px] text-[var(--text-muted)] font-mono mt-2 leading-relaxed">
        Sprint 33b wires the three cards above to the real Tauri
        IPC commands in <code>src-tauri/src/commands.rs</code>
        (<code>start_record</code> / <code>start_train</code> /
        <code> activate_model</code>). The Rust pipeline opens
        the mic via cpal, writes 30 s WAV chunks to
        <code> ~/.gundam-halo/recordings/yue-self-&lt;date&gt;/</code>,
        transcribes each chunk in a parallel Python
        <code> whisper_hf_helper</code> subprocess, and patches
        <code> config.toml</code> via <code>toml_edit</code> on
        activate. The status badge on each card mirrors the
        <code> phase</code> field of the IPC response. See
        <code> docs/FEATURE-SPEC-SPRINT26.md</code> §4.1 +
        Appendix C for the full UX.
      </p>
    </Section>
  );
}

/** Card shape used by all 3 Personalised Fine-tune cards.
 *  Extracted from the 3 inline JSX blocks in the original
 *  VoiceTab (Record / Train / Swap blocks are 30-40 LoC each
 *  and identical except for one button label + one paragraph
 *  + the IPC command name). */
function Card({
  title,
  description,
  phase,
  message,
  buttonLabel,
  onStart,
  testIdSuffix,
}: {
  title: string;
  description: React.ReactNode;
  phase: CardPhase;
  message: string;
  buttonLabel: string;
  onStart: () => void;
  testIdSuffix: "record" | "train" | "swap";
}) {
  return (
    <HudCard
      className="p-3"
      data-testid={`personalised-finetune-${testIdSuffix}-card`}
    >
      <div className="flex items-center justify-between mb-2">
        <h5 className="text-[11px] font-[Orbitron] text-[var(--accent)] uppercase tracking-widest">
          {title}
        </h5>
        <span
          className="text-[9px] font-mono text-[var(--text-muted)] uppercase"
          data-testid={`${testIdSuffix}-card-status`}
        >
          {phase}
        </span>
      </div>
      <p className="text-[11px] font-mono text-[var(--text-muted)] mb-2 leading-relaxed">
        {description}
      </p>
      <button
        type="button"
        onClick={onStart}
        disabled={!isTauriRuntime()}
        data-testid={`personalised-finetune-${testIdSuffix}-button`}
        className="w-full px-2 py-1.5 text-[10px] uppercase tracking-wider font-[Rajdhani] border border-[var(--accent)] text-[var(--accent)] bg-[var(--bg-elevated)] hover:bg-[var(--accent)] hover:text-[var(--bg-primary)] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {buttonLabel}
      </button>
      {message && (
        <p
          className="mt-2 text-[10px] font-mono text-[var(--text-secondary)] leading-relaxed break-words"
          data-testid={`${testIdSuffix}-card-message`}
        >
          {message}
        </p>
      )}
    </HudCard>
  );
}

/** Record card — calls `start_record` (the Tauri side opens
 *  the mic via cpal, writes 30 s WAV chunks to
 *  `~/.gundam-halo/recordings/yue-self-<date>/`). Sprint
 *  33b added the parallel-transcription stream so each chunk
 *  is also fed through WhisperHFASR while the next chunk is
 *  being recorded. */
function RecordCard(props: {
  phase: CardPhase;
  message: string;
  onStart: () => void;
}) {
  return (
    <Card
      title="Record"
      description={
        <>
          Speak Cantonese for 30 minutes. The app saves 30s
          chunks to{" "}
          <code>~/.gundam-halo/recordings/yue-self-&lt;date&gt;/</code>{" "}
          and transcribes them in parallel using the v0.1.4
          WhisperHFASR backend. Auto-stops at 30 min; you can
          stop early (min 10 min) or extend (max 60 min).
        </>
      }
      buttonLabel="Start recording"
      testIdSuffix="record"
      {...props}
    />
  );
}

/** Train card — calls `start_train`. The Rust side spawns
 *  the LoRA fine-tune subprocess (which uses 8 trainable
 *  params of the Whisper base, 1-epoch on M-series is ~1
 *  hour wall clock). */
function TrainCard(props: {
  phase: CardPhase;
  message: string;
  onStart: () => void;
}) {
  return (
    <Card
      title="Train"
      description={
        <>
          Run the personalised fine-tune. Loads the v0.1.4
          Common Voice yue checkpoint as the base, fine-tunes
          on your self-record corpus (1 hour wall clock on
          M-series). Output lands at{" "}
          <code>~/.gundam-halo/models/whisper-yue-self-&lt;date&gt;/</code>.
        </>
      }
      buttonLabel="Start training"
      testIdSuffix="train"
      {...props}
    />
  );
}

/** Swap card — calls `activate_model`. The Rust side
 *  patches `voice.asr.model_path` in `$HALO_HOME/config.toml`
 *  to point at the new checkpoint and restarts the backend. */
function SwapCard(props: {
  phase: CardPhase;
  message: string;
  onStart: () => void;
}) {
  return (
    <Card
      title="Swap"
      description={
        <>
          Activate the personalised model — points{" "}
          <code>voice.asr.model_path</code> at the new
          checkpoint in <code>~/.gundam-halo/config.toml</code>
          and restarts the backend. Previous v0.1.4 checkpoint
          is kept as a fallback (revert via git checkout).
        </>
      }
      buttonLabel="Activate personalised model"
      testIdSuffix="swap"
      {...props}
    />
  );
}
