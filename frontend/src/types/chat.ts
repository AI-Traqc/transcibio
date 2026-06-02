export type ChatCitation = {
  id: string;
  citation_index: number;
  segment_id: string;
  start_ms: number;
  end_ms: number;
  quote_excerpt: string;
};

export type ChatArtifact = {
  id: string;
  file_path: string;
  file_name: string;
  mime_type: string;
  size_bytes: number;
  kind: string;
  created_at_utc: string;
  action_proposal_id: string | null;
  session_id: string;
};

export type ChatActionProposal = {
  id: string;
  action_type: string;
  title: string;
  status: string;
  requires_confirmation: boolean;
  preview_markdown: string;
  payload: Record<string, unknown>;
  created_at_utc: string;
  updated_at_utc: string;
  executed_at_utc: string | null;
  error_message: string;
  executions: Array<Record<string, unknown>>;
  artifacts: ChatArtifact[];
};

export type ChatMessage = {
  id: string;
  thread_id: string;
  session_id: string;
  transcript_revision_id: string | null;
  role: string;
  content_markdown: string;
  content_plain_text: string;
  source_kind: string;
  status: string;
  model_name: string;
  created_at_utc: string;
  metadata: Record<string, unknown>;
  citations: ChatCitation[];
  action_proposals: ChatActionProposal[];
};

export type ChatThread = {
  id: string;
  session_id: string;
  title: string;
  created_at_utc: string;
  updated_at_utc: string;
};

export type SessionChatResponse = {
  session_id: string;
  thread: ChatThread | null;
  messages: ChatMessage[];
};

export type CreateChatMessageRequest = {
  text: string;
  source_kind?: "typed" | "voice_command";
  transcript_revision_id?: string | null;
};

export type CreateChatMessageResponse = {
  thread_id: string;
  user_message_id: string;
  assistant_message_id: string;
  job_id: string;
  status: string;
};

export type ActionMutationResponse = {
  action: ChatActionProposal;
};
