"use client";

import { useEffect, useState } from "react";

/** Light/dark toggle — persists to localStorage, applies [data-theme] on <html>. */
export function ThemeToggle() {
  const [dark, setDark] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    setDark(document.documentElement.dataset.theme === "dark");
  }, []);

  const toggle = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.dataset.theme = next ? "dark" : "light";
    try {
      localStorage.setItem("pmi-theme", next ? "dark" : "light");
    } catch {
      // storage unavailable — session-only theme
    }
  };

  return (
    <button
      onClick={toggle}
      className="btn btn-sm justify-center"
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      title={dark ? "Light mode" : "Dark mode"}
    >
      {mounted ? (dark ? "☀️" : "🌙") : "◐"}
    </button>
  );
}
