import { Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/providers/theme-provider";

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === "dark";
  return <Button variant="ghost" size="sm" onClick={toggleTheme} aria-label={`Switch to ${isDark ? "light" : "dark"} theme`}><>{isDark ? <Sun size={17} /> : <Moon size={17} />}</></Button>;
}
