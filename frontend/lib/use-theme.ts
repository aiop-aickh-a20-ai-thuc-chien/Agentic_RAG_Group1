"use client";

import { useEffect, useState } from "react";

export type Theme = "light" | "dark";

const THEME_KEY = "agentic-rag:theme:v1";

/**
 * Theme sáng/tối lưu localStorage, dùng chung giữa các trang.
 * Khởi tạo "light" để khớp SSR, đọc giá trị đã lưu trong useEffect (tránh hydration mismatch).
 */
export function useTheme(): { theme: Theme; isDark: boolean; toggleTheme: () => void } {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    const saved = window.localStorage.getItem(THEME_KEY);
    if (saved === "dark" || saved === "light") {
      setTheme(saved);
    }
  }, []);

  function toggleTheme() {
    setTheme((current) => {
      const next: Theme = current === "dark" ? "light" : "dark";
      try {
        window.localStorage.setItem(THEME_KEY, next);
      } catch {
        // localStorage bị chặn — vẫn đổi theme trong phiên.
      }
      return next;
    });
  }

  return { theme, isDark: theme === "dark", toggleTheme };
}
