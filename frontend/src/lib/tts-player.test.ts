/**
 * tts-player.test.ts — Sprint 60 A-A1 tests.
 *
 * 8 tests pinning the TtsPlayer contract. The class is extracted
 * from VoicePanel so the queue / drain / dispose logic can be
 * tested without React + AudioContext + voice WS subscriptions.
 *
 * Strategy: stub the `<audio>` element via a `createAudio` factory.
 * We DON'T mock `Blob` / `URL.createObjectURL` — jsdom provides
 * both natively. We DO override `audio.play()` to resolve
 * immediately (no user gesture in jsdom) and call `onended` to
 * fire the chunk-end path.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TtsPlayer } from "./tts-player";

/** Stub `<audio>` element. We replace `.play()` so jsdom doesn't
 *  throw on autoplay-policy rejection. The `triggerEnd()` helper
 *  fires `onended` so tests can advance through the queue. */
interface StubAudio extends HTMLAudioElement {
  triggerEnd: () => void;
  triggerError: () => void;
}

function createStubAudioFactory() {
  const audios: StubAudio[] = [];
  const factory = () => {
    const audio = new Audio() as StubAudio;
    audio.play = vi.fn().mockResolvedValue(undefined) as never;
    audio.triggerEnd = () => {
      const handler = audio.onended;
      if (handler) (handler as () => void).call(audio);
    };
    audio.triggerError = () => {
      const handler = audio.onerror;
      if (handler) {
        (handler as (e: Event) => void).call(audio, new Event("error"));
      }
    };
    audios.push(audio);
    return audio;
  };
  return { factory, audios };
}

/** Wait for several microtask + macrotask cycles. Useful after
 *  triggering async paths that resolve via Promise chains. */
async function flushTicks(n = 5): Promise<void> {
  for (let i = 0; i < n; i++) {
    await new Promise((r) => setTimeout(r, 0));
  }
}

describe("TtsPlayer (Sprint 60 A-A1)", () => {
  let factory: () => HTMLAudioElement;
  let audios: StubAudio[];

  beforeEach(() => {
    const f = createStubAudioFactory();
    factory = f.factory;
    audios = f.audios;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("creates a single shared audio element on first enqueue (lazy attach)", () => {
    const player = new TtsPlayer({ createAudio: factory });
    expect(player.getAudioElement()).toBeNull();

    player.enqueue(new Uint8Array([1, 2, 3]).buffer);
    expect(player.getAudioElement()).not.toBeNull();
    expect(audios).toHaveLength(1);

    player.enqueue(new Uint8Array([4, 5, 6]).buffer);
    expect(audios).toHaveLength(1);
  });

  it("drains chunks in order", async () => {
    const started: number[] = [];
    const player = new TtsPlayer({
      createAudio: factory,
      onChunkStart: (chunk) => started.push(chunk.byteLength),
    });

    player.enqueue(new Uint8Array([1, 1]).buffer);
    player.enqueue(new Uint8Array([2, 2, 2]).buffer);
    player.enqueue(new Uint8Array([3, 3, 3, 3]).buffer);

    // Trigger end-of-chunk on each audio element in turn. The
    // player's drain chain assigns `audio.src` to a fresh blob URL
    // on every chunk, so the LATEST audio element is the one
    // currently playing. We trigger end repeatedly — the early
    // ones are no-ops (onended was already nulled by cleanup).
    for (let i = 0; i < 3; i++) {
      await flushTicks(2);
      audios[audios.length - 1]?.triggerEnd();
    }
    await flushTicks(3);

    expect(started).toEqual([2, 3, 4]);
  });

  it("reset() bumps the play seq — in-flight drain aborts", async () => {
    const player = new TtsPlayer({ createAudio: factory });
    player.enqueue(new Uint8Array([1, 1]).buffer);
    player.enqueue(new Uint8Array([2, 2]).buffer);

    // Wait for the first chunk to start playing.
    await flushTicks(2);

    // Reset while the first chunk is in-flight. The drain chain
    // captures seq=0 at start; reset bumps to 1; the chain sees
    // mySeq !== playSeq and exits.
    player.reset();

    // Trigger end on the in-flight chunk — should NOT pick up
    // the cleared chunk 2.
    audios[0].triggerEnd();
    await flushTicks(3);

    expect(player.isDraining).toBe(false);
  });

  it("enqueue() after dispose() is a no-op", () => {
    const player = new TtsPlayer({ createAudio: factory });
    player.dispose();
    player.enqueue(new Uint8Array([1, 1]).buffer);
    expect(player.getAudioElement()).toBeNull();
    expect(player.isDisposed).toBe(true);
  });

  it("dispose() is idempotent", () => {
    const player = new TtsPlayer({ createAudio: factory });
    player.dispose();
    player.dispose();
    player.dispose();
    expect(player.isDisposed).toBe(true);
  });

  it("empty enqueue is a silent no-op (no crash, no audio element created)", () => {
    const player = new TtsPlayer({ createAudio: factory });
    player.enqueue(new ArrayBuffer(0));
    expect(player.getAudioElement()).toBeNull();
    expect(audios).toHaveLength(0);
  });

  it("audio.play() rejection doesn't kill the queue (next chunk still plays)", async () => {
    // Wrap the factory so the lazily-created element's play()
    // is replaced with a rejecting mock BEFORE the player's
    // drain chain calls it. This is what happens in real life
    // when autoplay policy blocks the chunk.
    const wrapFactory = () => {
      const a = factory();
      a.play = vi
        .fn()
        .mockRejectedValue(new Error("autoplay blocked")) as never;
      return a;
    };
    const onChunkEnd = vi.fn();
    const player = new TtsPlayer({
      createAudio: wrapFactory,
      onChunkEnd,
    });

    player.enqueue(new Uint8Array([1, 1]).buffer);
    player.enqueue(new Uint8Array([2, 2]).buffer);

    await flushTicks(10);

    // First chunk's play() rejected → cleanup ran → resolve fired →
    // await unblocked → drain loop picked up chunk 2 → second play()
    // also rejected → cleanup ran → drain loop exited.
    expect(player.isDraining).toBe(false);
    expect(onChunkEnd).toHaveBeenCalledTimes(2);
  });

  it("audio.onerror fires the chunk-end path (does not hang the queue)", async () => {
    const onChunkEnd = vi.fn();
    const player = new TtsPlayer({
      createAudio: factory,
      onChunkEnd,
    });

    player.enqueue(new Uint8Array([1, 1]).buffer);
    player.enqueue(new Uint8Array([2, 2, 2]).buffer);

    await flushTicks(2);
    audios[0].triggerError();

    await flushTicks(3);
    audios[audios.length - 1].triggerEnd();
    await flushTicks(3);

    expect(onChunkEnd).toHaveBeenCalledTimes(2);
    expect(player.isDraining).toBe(false);
  });
});