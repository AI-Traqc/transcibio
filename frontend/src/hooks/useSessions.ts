import { useCallback, useEffect, useRef, useState } from "react";
import * as sessionsApi from "@/api/sessions";
import type { SessionRecord, CreateSessionRequest } from "@/types/session";

export interface UseSessionsResult {
  sessions: SessionRecord[];
  loading: boolean;
  error: string | null;
  query: string;
  setQuery: (q: string) => void;
  refresh: () => Promise<void>;
  create: (body?: Partial<CreateSessionRequest>) => Promise<SessionRecord>;
  rename: (id: string, title: string) => Promise<SessionRecord>;
  remove: (id: string) => Promise<void>;
  removeAll: () => Promise<number>;
}

export function useSessions(): UseSessionsResult {
  const [sessions, setSessions] = useState<SessionRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQueryState] = useState<string>("");

  const debouncedQueryRef = useRef<number | null>(null);

  const load = useCallback(async (q: string) => {
    setLoading(true);
    setError(null);
    try {
      const list = await sessionsApi.listSessions({ q, limit: 100 });
      setSessions(list);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load sessions");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load("");
  }, [load]);

  const setQuery = useCallback(
    (next: string) => {
      setQueryState(next);
      if (debouncedQueryRef.current) {
        window.clearTimeout(debouncedQueryRef.current);
      }
      debouncedQueryRef.current = window.setTimeout(() => {
        void load(next);
      }, 220);
    },
    [load],
  );

  const refresh = useCallback(() => load(query), [load, query]);

  const create = useCallback(
    async (body: Partial<CreateSessionRequest> = {}) => {
      const record = await sessionsApi.createSession({
        title: body.title ?? "New session",
        source_kind: body.source_kind ?? "upload",
        source_name: body.source_name ?? "",
        source_language_hint: body.source_language_hint ?? "auto",
        command_language_hint: body.command_language_hint ?? "auto",
      });
      setSessions((prev) => [record, ...prev]);
      return record;
    },
    [],
  );

  const rename = useCallback(async (id: string, title: string) => {
    const updated = await sessionsApi.renameSession(id, { title });
    setSessions((prev) => prev.map((s) => (s.id === id ? updated : s)));
    return updated;
  }, []);

  const remove = useCallback(async (id: string) => {
    await sessionsApi.deleteSession(id);
    setSessions((prev) => prev.filter((s) => s.id !== id));
  }, []);

  const removeAll = useCallback(async () => {
    const result = await sessionsApi.deleteAllSessions();
    setSessions([]);
    return result.deleted_count;
  }, []);

  return {
    sessions,
    loading,
    error,
    query,
    setQuery,
    refresh,
    create,
    rename,
    remove,
    removeAll,
  };
}
