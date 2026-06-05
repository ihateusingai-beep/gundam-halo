import { create } from "zustand";
import { api } from "@/lib/api";
import type { ProjectSummary } from "@/types/api";

interface ProjectsState {
  projects: ProjectSummary[];
  loading: boolean;
  error: string | null;
  fetchProjects: () => Promise<void>;
  createProject: (name: string, description?: string) => Promise<ProjectSummary>;
  archiveProject: (name: string) => Promise<void>;
  deleteProject: (name: string) => Promise<void>;
}

export const useProjectsStore = create<ProjectsState>((set, get) => ({
  projects: [],
  loading: false,
  error: null,

  fetchProjects: async () => {
    set({ loading: true, error: null });
    try {
      const projects = await api.listProjects();
      set({ projects, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  createProject: async (name, description) => {
    const proj = await api.createProject({ name, description });
    set({ projects: [...get().projects, proj] });
    return proj;
  },

  archiveProject: async (name) => {
    await api.archiveProject(name);
    set({
      projects: get().projects.map((p) =>
        p.name === name ? { ...p, status: "archived" } : p,
      ),
    });
  },

  deleteProject: async (name) => {
    await api.deleteProject(name);
    set({ projects: get().projects.filter((p) => p.name !== name) });
  },
}));
