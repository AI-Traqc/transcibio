import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "transcibio.sidebar.collapsed";

function readStored(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(STORAGE_KEY) === "true";
}

export interface UseSidebarResult {
  collapsed: boolean;
  setCollapsed: (value: boolean) => void;
  toggle: () => void;
}

export function useSidebar(): UseSidebarResult {
  const [collapsed, setCollapsedState] = useState<boolean>(() => readStored());

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(STORAGE_KEY, String(collapsed));
  }, [collapsed]);

  const setCollapsed = useCallback((value: boolean) => {
    setCollapsedState(value);
  }, []);

  const toggle = useCallback(() => {
    setCollapsedState((prev) => !prev);
  }, []);

  return { collapsed, setCollapsed, toggle };
}
