import { CyberWaveform } from "@/components/gundam/CyberWaveform";
import { HoloPanel } from "@/components/gundam/HoloPanel";

/**
 * CyberWaveformDemo — sandbox for the cyber oscilloscope widget.
 *
 * The primary use is in the cockpit's "AVATAR" panel via
 * CSSAvatar (now powered by the 88-frame Unicorn sprite sheet
 * and the shared amplitude source). This demo page shows the
 * CyberWaveform alone in different layer counts.
 */
export function CyberWaveformDemo() {
  return (
    <div
      className="min-h-screen w-full flex flex-col items-center justify-center gap-10 p-8"
      style={{ background: "#050b1a" }}
    >
      <h1
        className="text-2xl font-mono tracking-widest"
        style={{ color: "rgba(0, 229, 255, 0.85)" }}
      >
        CYBER OSCILLOSCOPE // VARIANTS
      </h1>

      <HoloPanel title="PRIMARY // 6 LAYERS" className="w-full max-w-4xl">
        <CyberWaveform layers={6} height={220} />
      </HoloPanel>

      <HoloPanel title="SPARSE // 3 LAYERS" className="w-full max-w-4xl">
        <CyberWaveform layers={3} height={140} speed={0.06} />
      </HoloPanel>

      <HoloPanel title="DENSE // 10 LAYERS" className="w-full max-w-4xl">
        <CyberWaveform layers={10} height={180} speed={0.1} />
      </HoloPanel>

      <HoloPanel title="CHAOTIC // FAST" className="w-full max-w-4xl">
        <CyberWaveform layers={8} height={120} speed={0.18} />
      </HoloPanel>

      <p
        className="text-xs font-mono opacity-50"
        style={{ color: "rgba(255, 0, 200, 0.7)" }}
      >
        // shared amplitude source // sprite sheet 88f @ 30fps //
        // avatar scale 1.0 → 1.18 + glow on each pulse //
      </p>
    </div>
  );
}

export default CyberWaveformDemo;
