import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "transcibio.selectedSessionId";

function readStored(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(STORAGE_KEY);
}

export interface UseSessionResult {
  selectedSessionId: string | null;
  select: (id: string | null) => void;
}

export function useSession(): UseSessionResult {
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(
    () => readStored(),
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (selectedSessionId === null) {
      window.localStorage.removeItem(STORAGE_KEY);
    } else {
      window.localStorage.setItem(STORAGE_KEY, selectedSessionId);
    }
  }, [selectedSessionId]);

  const select = useCallback((id: string | null) => {
    setSelectedSessionId(id);
  }, []);

  return { selectedSessionId, select };
}
