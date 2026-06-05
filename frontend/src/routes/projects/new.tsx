import { useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import { HudCard } from "@/components/gundam/HudCard";
import { CommandInput } from "@/components/gundam/CommandInput";
import { useProjectsStore } from "@/stores/projects";
import { ApiError } from "@/lib/api";

/** New project wizard — minimal: name + description. With toast feedback. */
export function NewProjectPage() {
  const navigate = useNavigate();
  const { createProject } = useProjectsStore();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (text: string) => {
    setName(text);
    await doCreate(text, description);
  };

  const doCreate = async (projectName: string, desc: string) => {
    if (!projectName.match(/^[a-z0-9-]+$/)) {
      const msg = "Project name must be lowercase letters, numbers, and hyphens only.";
      setError(msg);
      toast.error("Invalid name", { description: msg });
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await createProject(projectName, desc);
      toast.success("Project created", {
        description: `Welcome to ${projectName}`,
      });
      navigate(`/projects/${projectName}`);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      setError(msg);
      toast.error("Failed to create project", { description: msg });
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
