import { useState, type FormEvent } from "react";
import { cn } from "@/lib/utils";

interface CommandInputProps {
  onSubmit: (text: string) => void | Promise<void>;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}

/** Chat-style command input with Gundam styling. */
export function CommandInput({
  onSubmit,
  placeholder = "Type a command...",
  disabled,
  className,
}: CommandInputProps) {
  const [value, setValue] = useState("");

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!value.trim() || disabled) return;
    await onSubmit(value.trim());
    setValue("");
  };

  return (
    <form
      onSubmit={handleSubmit}
      className={cn(
        "flex items-center gap-2 px-4 py-2",
        "border border-[var(--border-color)] rounded-md",
        "bg-[var(--bg-card)] backdrop-blur-md gundam-holo",
        className,
      )}
    >
      <span className="text-[var(--accent)] font-[Orbitron] text-sm">{">"}</span>
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className={cn(
          "flex-1 bg-transparent outline-none",
          "text-[var(--text-primary)] placeholder:text-[var(--text-muted)]",
          "font-mono text-sm",
        )}
      />
      <button
        type="submit"
        disabled={disabled || !value.trim()}
        className={cn(
          "px-3 py-1 rounded text-xs",
          "border border-[var(--accent)] text-[var(--accent)]",
          "hover:bg-[var(--accent)] hover:text-[var(--bg-primary)]",
          "disabled:opacity-50 disabled:cursor-not-allowed",
          "transition-colors font-[Rajdhani] uppercase tracking-wider",
        )}
      >
        Send
      </button>
    </form>
  );
}
