export type TranscriptRevisionSummary = {
  id: string;
  revision_number: number;
  created_at_utc: string;
  created_by: string;
  source: string;
  parent_revision_id: string | null;
  language_detected: string;
  diarization_used: boolean;
  stt_model: string;
  warnings: string[];
};

export type TranscriptSpeaker = {
  id: string;
  speaker_key: string;
  display_name: string;
  sort_order: number;
};

export type TranscriptSegment = {
  id: string;
  segment_index: number;
  speaker_id: string | null;
  speaker_key: string | null;
  speaker_display_name: string | null;
  start_ms: number;
  end_ms: number;
  text: string;
  confidence: number | null;
  word_count: number;
};

export type TranscriptResponse = {
  session_id: string;
  revision: TranscriptRevisionSummary;
  speakers: TranscriptSpeaker[];
  segments: TranscriptSegment[];
};

export type TranscriptCorrectionSegmentChange = {
  segment_id: string;
  segment_index: number;
  start_ms: number;
  end_ms: number;
  before_text: string;
  after_text: string;
};

export type TranscriptCorrectionProposalResponse = {
  proposal_id: string;
  session_id: string;
  base_revision_id: string;
  strategy_used: string;
  model_name: string;
  changed_segment_count: number;
  warnings: string[];
  diff_preview: Record<string, unknown>;
  segment_changes: TranscriptCorrectionSegmentChange[];
};

export type ApplyTranscriptCorrectionResponse = {
  proposal_id: string;
  status: string;
  applied_revision_id: string;
  revision_number: number;
  changed_segment_count: number;
  transcript: TranscriptResponse;
};

export type CorrectionScopeType =
  | "full_transcript"
  | "segment_ids"
  | "time_range_ms";

export type CorrectionStrategy = "auto" | "llm" | "rules";

export type CreateCorrectionProposalRequest = {
  revision_id: string | null;
  scope_type: CorrectionScopeType;
  segment_ids: string[];
  start_ms: number | null;
  end_ms: number | null;
  strategy: CorrectionStrategy;
};
