import { useMemo, useState } from "react";
import { toast } from "sonner";
import { ChatView } from "@/components/chat/ChatView";
import { DeleteDialog } from "@/components/dialogs/DeleteDialog";
import { RenameDialog } from "@/components/dialogs/RenameDialog";
import { SettingsDialog } from "@/components/dialogs/SettingsDialog";
import { Sidebar } from "@/components/sidebar/Sidebar";
import { useDisclosure } from "@/hooks/useDisclosure";
import { useSession } from "@/hooks/useSession";
import { useSessions } from "@/hooks/useSessions";
import { useSettings } from "@/hooks/useSettings";
import { useSidebar } from "@/hooks/useSidebar";
import type { SessionRecord } from "@/types/session";

export function AppShell() {
  const sessions = useSessions();
  const { selectedSessionId, select } = useSession();
  const settings = useSettings();
  const sidebar = useSidebar();

  const settingsDialog = useDisclosure();
  const renameDialog = useDisclosure<SessionRecord>();
  const deleteDialog = useDisclosure<SessionRecord>();

  const [renameBusy, setRenameBusy] = useState(false);
  const [renameError, setRenameError] = useState<string | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [settingsSaveError, setSettingsSaveError] = useState<string | null>(null);

  const session = useMemo(
    () =>
      sessions.sessions.find((s) => s.id === selectedSessionId) ?? null,
    [sessions.sessions, selectedSessionId],
  );

  const handleNewSession = async () => {
    try {
      const record = await sessions.create();
      select(record.id);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to create session");
    }
  };

  const handleRename = async (title: string) => {
    if (!renameDialog.payload) return;
    setRenameBusy(true);
    setRenameError(null);
    try {
      await sessions.rename(renameDialog.payload.id, title);
      renameDialog.hide();
      toast.success("Session renamed");
    } catch (err) {
      setRenameError(err instanceof Error ? err.message : "Rename failed");
    } finally {
      setRenameBusy(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteDialog.payload) return;
    const id = deleteDialog.payload.id;
    setDeleteBusy(true);
    setDeleteError(null);
    try {
      await sessions.remove(id);
      if (selectedSessionId === id) {
        const next = sessions.sessions.find((s) => s.id !== id);
        select(next?.id ?? null);
      }
      deleteDialog.hide();
      toast.success("Session deleted");
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setDeleteBusy(false);
    }
  };

  const handleSaveSettings = async (patch: Parameters<typeof settings.save>[0]) => {
    setSettingsSaveError(null);
    try {
      await settings.save(patch);
      toast.success("Settings saved");
    } catch (err) {
      setSettingsSaveError(err instanceof Error ? err.message : "Failed to save");
      throw err;
    }
  };

  const handleDeleteAllSessions = async () => {
    try {
      const count = await sessions.removeAll();
      select(null);
      toast.success(count > 0 ? `Deleted ${count} session(s)` : "No sessions to delete");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to delete sessions");
      throw err;
    }
  };

  return (
    <div className="flex h-screen w-full bg-background text-foreground">
      <Sidebar
        sessions={sessions.sessions}
        selectedSessionId={selectedSessionId}
        loading={sessions.loading}
        collapsed={sidebar.collapsed}
        query={sessions.query}
        onQueryChange={sessions.setQuery}
        onSelectSession={select}
        onNewSession={handleNewSession}
        onRenameSession={(s) => renameDialog.show(s)}
        onDeleteSession={(s) => deleteDialog.show(s)}
        onToggleCollapse={sidebar.toggle}
        onOpenSettings={settingsDialog.show}
      />
      <main className="flex h-full flex-1 flex-col overflow-hidden">
        <ChatView
          session={session}
          settings={settings.settings}
          onNewSession={handleNewSession}
          onSessionsRefresh={sessions.refresh}
        />
      </main>

      <SettingsDialog
        open={settingsDialog.open}
        settings={settings.settings}
        busy={settings.loading}
        error={settingsSaveError ?? settings.error}
        onOpenChange={settingsDialog.onOpenChange}
        onSave={handleSaveSettings}
        onDeleteAllSessions={handleDeleteAllSessions}
      />
      <RenameDialog
        open={renameDialog.open}
        session={renameDialog.payload}
        busy={renameBusy}
        error={renameError}
        onOpenChange={renameDialog.onOpenChange}
        onConfirm={handleRename}
      />
      <DeleteDialog
        open={deleteDialog.open}
        session={deleteDialog.payload}
        busy={deleteBusy}
        error={deleteError}
        onOpenChange={deleteDialog.onOpenChange}
        onConfirm={handleDelete}
      />
    </div>
  );
}
