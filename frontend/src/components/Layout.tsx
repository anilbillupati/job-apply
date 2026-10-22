import { History, KeyRound, Monitor, Moon, Plus, Radar, Settings, Sun } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useTheme, type Theme } from "@/hooks/useTheme";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/new", label: "New search", icon: Plus },
  { to: "/runs", label: "Runs", icon: History },
  { to: "/keys", label: "API keys", icon: KeyRound },
  { to: "/settings", label: "Settings", icon: Settings },
];

const NEXT_THEME: Record<Theme, Theme> = { system: "light", light: "dark", dark: "system" };
const THEME_ICON = { system: Monitor, light: Sun, dark: Moon };

export function Layout() {
  const { theme, setTheme } = useTheme();
  const ThemeIcon = THEME_ICON[theme];
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b bg-background/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-2 px-4">
          <NavLink to="/" className="mr-2 flex items-center gap-2 font-semibold">
            <Radar className="h-5 w-5 text-primary" />
            <span className="hidden sm:inline">JobRadar</span>
          </NavLink>
          <nav className="flex flex-1 items-center gap-1">
            {NAV.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
                    isActive && "bg-accent text-foreground",
                  )
                }
              >
                <Icon className="h-4 w-4" />
                <span className="hidden sm:inline">{label}</span>
              </NavLink>
            ))}
          </nav>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setTheme(NEXT_THEME[theme])}
            title={`Theme: ${theme} (click to change)`}
            aria-label={`Theme: ${theme}`}
          >
            <ThemeIcon />
          </Button>
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
