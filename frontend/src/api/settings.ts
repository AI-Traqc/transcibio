import { apiFetch, apiFetchJson } from "./client";
import type {
  ModelsResponse,
  SettingsPatchRequest,
  SettingsPayload,
} from "@/types/settings";

export function getSettings(): Promise<SettingsPayload> {
  return apiFetch<SettingsPayload>("/api/v1/settings");
}

export function patchSettings(
  body: SettingsPatchRequest,
): Promise<SettingsPayload> {
  return apiFetchJson<SettingsPayload>("/api/v1/settings", "PATCH", body);
}

export function getAvailableModels(): Promise<ModelsResponse> {
  return apiFetch<ModelsResponse>("/api/v1/settings/models");
}
