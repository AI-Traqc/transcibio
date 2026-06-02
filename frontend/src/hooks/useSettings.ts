import { useCallback, useEffect, useState } from "react";
import * as settingsApi from "@/api/settings";
import type {
  SettingsPatchRequest,
  SettingsPayload,
} from "@/types/settings";

export interface UseSettingsResult {
  settings: SettingsPayload | null;
  loading: boolean;
  error: string | null;
  save: (patch: SettingsPatchRequest) => Promise<SettingsPayload>;
  refresh: () => Promise<void>;
}

export function useSettings(): UseSettingsResult {
  const [settings, setSettings] = useState<SettingsPayload | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await settingsApi.getSettings();
      setSettings(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const save = useCallback(async (patch: SettingsPatchRequest) => {
    const updated = await settingsApi.patchSettings(patch);
    setSettings(updated);
    return updated;
  }, []);

  return { settings, loading, error, save, refresh: load };
}
