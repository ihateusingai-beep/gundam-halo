import { useParams } from "react-router";
import { HudCard } from "@/components/gundam/HudCard";

/** Project memory browser — placeholder. */
export function ProjectMemoryPage() {
  const { id } = useParams<{ id: string }>();
  return (
    <HudCard>
      <h2 className="text-2xl font-[Orbitron] text-[var(--accent)] tracking-widest uppercase mb-3">
        Memory: {id}
      </h2>
      <p className="text-sm text-[var(--text-secondary)]">
        Memory browser — coming soon. Will show per-project memory entries, file references, tool call logs.
      </p>
    </HudCard>
  );
}
