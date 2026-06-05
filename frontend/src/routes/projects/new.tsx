import { useState } from "react";
import { useNavigate } from "react-router";
import { HudCard } from "@/components/gundam/HudCard";
import { CommandInput } from "@/components/gundam/CommandInput";
import { useProjectsStore } from "@/stores/projects";

/** New project wizard — minimal: name + description. */
export function NewProjectPage() {
  const navigate = useNavigate();
  const { createProject } = useProjectsStore();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (text: string) => {
    // Simple: text is the project name
    setName(text);
    await doCreate(text, description);
  };

  const doCreate = async (projectName: string, desc: string) => {
    if (!projectName.match(/^[a-z0-9-]+$/)) {
      setError("Project name must be lowercase letters, numbers, and hyphens only.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await createProject(projectName, desc);
      navigate(`/projects/${projectName}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <HudCard>
      <h2 className="text-2xl font-[Orbitron] text-[var(--accent)] tracking-widest uppercase mb-4">
        New Project
      </h2>

      <div className="space-y-4">
        <div>
          <label className="block text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1 font-[Rajdhani]">
            Project Name
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. fix-jarvis-memory-leak"
            className="w-full px-3 py-2 bg-[var(--bg-input)] border border-[var(--border-color)] rounded text-[var(--text-primary)] font-mono text-sm focus:outline-none focus:border-[var(--accent)]"
          />
          <p className="text-[10px] text-[var(--text-muted)] mt-1">
            Lowercase letters, numbers, hyphens. Used as directory name.
          </p>
        </div>

        <div>
          <label className="block text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1 font-[Rajdhani]">
            Description (optional)
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What is this project for?"
            rows={3}
            className="w-full px-3 py-2 bg-[var(--bg-input)] border border-[var(--border-color)] rounded text-[var(--text-primary)] font-mono text-sm focus:outline-none focus:border-[var(--accent)]"
          />
        </div>

        {error && (
          <div className="text-sm text-[var(--danger)] font-mono">⚠ {error}</div>
        )}

        <div className="flex items-center justify-between pt-2">
          <button
            onClick={() => doCreate(name, description)}
            disabled={busy || !name}
            className="px-4 py-2 border border-[var(--accent)] text-[var(--accent)] rounded hover:bg-[var(--accent)] hover:text-[var(--bg-primary)] transition-colors text-sm font-[Rajdhani] uppercase tracking-wider disabled:opacity-50"
          >
            {busy ? "Creating..." : "Create"}
          </button>
          <span className="text-xs text-[var(--text-muted)] font-mono">or quick-create:</span>
        </div>

        <CommandInput
          onSubmit={handleSubmit}
          placeholder="Or just type a project name and press Enter..."
          disabled={busy}
        />
      </div>
    </HudCard>
  );
}
