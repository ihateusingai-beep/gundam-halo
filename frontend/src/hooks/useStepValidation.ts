/**
 * useStepValidation — Zod-backed validation hook for wizard steps.
 *
 * Sprint 63 W-A4 (pilot). Pre-existing: each wizard step
 * hand-rolled its own validation. Centralizing via Zod:
 *
 *   - 1 source of truth per step (the schema)
 *   - TypeScript inference from the schema (no separate type)
 *   - Stable `{ field, message }` error shape that maps
 *     1:1 to the existing `WizardError[]` contract
 *
 * ## API
 *
 *   ```ts
 *   import { z } from "zod";
 *   import { useStepValidation } from "@/hooks/useStepValidation";
 *
 *   const llmSchema = z.object({
 *     provider: z.enum(["minimax", "openai", "anthropic", "ollama"]),
 *     api_key: z.string().min(1, "API key is required"),
 *     base_url: z.string().url("Base URL must be a valid URL"),
 *     default_model: z.string().min(1, "Default model is required"),
 *   });
 *
 *   function StepLLM({ form, errors, ... }) {
 *     const [draft, setDraft] = useState(form);
 *     const validation = useStepValidation(llmSchema, draft);
 *     // ...
 *   }
 *   ```
 *
 * ## Memoisation
 *
 *  The hook re-validates ONLY when `draft` changes (via
 *  `useMemo` with `[draft, schema]` as deps). Re-renders that
 *  don't change the draft don't re-run the validation — a
 *  key property for forms where every keystroke would
 *  otherwise re-validate 100+ fields.
 */
import { useMemo } from "react";
import type { ZodType } from "zod";

export interface StepValidationError {
  /** Path to the field (e.g. `"api_key"`, `"base_url"`). */
  field: string;
  /** Human-readable error message. */
  message: string;
}

export interface StepValidationResult {
  ok: boolean;
  errors: StepValidationError[];
}

export function useStepValidation<T>(
  schema: ZodType<T>,
  draft: T,
): StepValidationResult {
  return useMemo<StepValidationResult>(() => {
    const result = schema.safeParse(draft);
    if (result.success) {
      return { ok: true, errors: [] };
    }
    // Zod returns issues with `.path` (array of keys) and
    // `.message` (human-readable). Flatten to the shape the
    // existing wizard expects.
    const errors: StepValidationError[] = result.error.issues.map(
      (issue) => ({
        field: issue.path.join(".") || "(root)",
        message: issue.message,
      }),
    );
    return { ok: false, errors };
  }, [schema, draft]);
}