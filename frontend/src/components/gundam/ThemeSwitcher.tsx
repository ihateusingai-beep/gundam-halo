import { useThemeStore } from "@/stores/theme";
import type { GundamTheme, ThemeInfo } from "@/types/api";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export const THEMES: ThemeInfo[] = [
  { id: "gundam-ntd", name: "NT-D", emoji: "🦄", description: "Unicorn psychoframe" },
  { id: "gundam-seed", name: "SEED", emoji: "⚡", description: "Freedom prismatic" },
  { id: "gundam-crossbone", name: "CROSS", emoji: "💀", description: "X-1 skull" },
  { id: "gundam-ntd-green", name: "GREEN", emoji: "🌿", description: "Green Frame" },
  { id: "gundam-00", name: "00", emoji: "🌐", description: "Qubit Trans-Am" },
  { id: "gundam-destiny", name: "DESTINY", emoji: "⚔", description: "Beam blade" },
  { id: "gundam-god", name: "GOD", emoji: "🔥", description: "Flame of God" },
  { id: "gundam-cartoon", name: "KAWAII", emoji: "✨", description: "Cartoon chibi" },
];

/** Floating 8-mode theme switcher (always visible, bottom-right). */
export function ThemeSwitcher() {
  const { theme, setTheme } = useThemeStore();

  return (
    <div
      style={{
        position: "fixed",
        bottom: 24,
        right: 24,
        zIndex: 9999,
      }}
    >
      <DropdownMenu>
        <DropdownMenuTrigger
          className="w-[72px] h-[72px] rounded-full border-[3px] border-white cursor-pointer text-2xl"
          style={{
            background: "linear-gradient(135deg, #FF69B4, #00D4FF, #FFD700)",
          }}
          aria-label="Toggle Gundam theme switcher"
        >
          🎮
          <span style={{ display: "block", fontSize: 10, marginTop: 2 }}>
            MS MODE
          </span>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          align="end"
          side="top"
          sideOffset={8}
          className="min-w-32"
        >
          <DropdownMenuRadioGroup
            value={theme ?? ""}
            onValueChange={(v) => setTheme(v as GundamTheme)}
          >
            {THEMES.map((t) => (
              <DropdownMenuRadioItem key={t.id} value={t.id ?? ""}>
                <span className="font-[Rajdhani] uppercase tracking-wider text-xs">
                  {t.emoji} {t.name}
                </span>
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onClick={() => setTheme(null as unknown as GundamTheme)}
            className="text-gray-400 focus:text-gray-200"
          >
            <span className="font-[Rajdhani] uppercase tracking-wider text-xs">
              ✖ OFF
            </span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
