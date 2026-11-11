export type ThemePreference = "light" | "dark" | "system";

/**
 * Apply a theme to the document and remember it for the pre-paint script in
 * app/layout.tsx. "system" clears the stored value so the OS preference wins.
 */
export function applyTheme(theme: ThemePreference): void {
  if (typeof document === "undefined") return;
  try {
    if (theme === "system") localStorage.removeItem("theme");
    else localStorage.setItem("theme", theme);
  } catch {
    // storage unavailable: still apply for this page view
  }
  const dark =
    theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}
