import { useEffect, useState } from "react";

export type Appearance = "system" | "light" | "dark";

export function useAppearance() {
  const [appearance, setAppearance] = useState<Appearance>(() => {
    try {
      const saved = localStorage.getItem("fileora.appearance");
      return saved === "light" || saved === "dark" || saved === "system"
        ? saved
        : "dark";
    } catch {
      return "dark";
    }
  });

  useEffect(() => {
    document.documentElement.dataset.theme = appearance;
    try {
      localStorage.setItem("fileora.appearance", appearance);
    } catch {
      // Appearance remains usable when browser storage is unavailable.
    }
  }, [appearance]);

  return { appearance, setAppearance };
}
