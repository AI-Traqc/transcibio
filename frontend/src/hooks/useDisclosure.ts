import { useCallback, useEffect, useState } from "react";

export interface UseDisclosureResult<TPayload> {
  open: boolean;
  payload: TPayload | null;
  show: (payload?: TPayload) => void;
  hide: () => void;
  toggle: () => void;
  onOpenChange: (next: boolean) => void;
}

export function useDisclosure<TPayload = undefined>(
  initialOpen = false,
  resetKey?: string | null,
): UseDisclosureResult<TPayload> {
  const [open, setOpen] = useState<boolean>(initialOpen);
  const [payload, setPayload] = useState<TPayload | null>(null);

  useEffect(() => {
    if (resetKey === undefined) return;
    setOpen(initialOpen);
    setPayload(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetKey]);

  const show = useCallback((next?: TPayload) => {
    if (next !== undefined) {
      setPayload(next);
    }
    setOpen(true);
  }, []);

  const hide = useCallback(() => {
    setOpen(false);
  }, []);

  const toggle = useCallback(() => {
    setOpen((prev) => !prev);
  }, []);

  const onOpenChange = useCallback((next: boolean) => {
    setOpen(next);
    if (!next) {
      setPayload(null);
    }
  }, []);

  return { open, payload, show, hide, toggle, onOpenChange };
}
