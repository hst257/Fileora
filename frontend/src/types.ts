export type Locator = {
  page?: number;
  line_start?: number;
  line_end?: number;
  start_ms?: number;
  end_ms?: number;
  symbol?: string;
};
export type Evidence = {
  chunk_id: number;
  kind: string;
  snippet: string;
  locator: Locator;
  symbol: string;
  asset_url: string | null;
};
export type Result = {
  file_id: number;
  name: string;
  path: string;
  relative_path: string;
  extension: string;
  modality: string;
  mtime_ns: number;
  size: number;
  score: number;
  ranking: string;
  match_kind?: "terms" | "semantic" | "visual";
  evidence: Evidence[];
  aliases: { id: number; relative_path: string; path: string }[];
  warnings: string[];
};
export type Root = {
  id: number;
  path: string;
  status: string;
  last_scan: string | null;
};
export type Status = {
  files: number;
  chunks: number;
  embeddings: number;
  generation: number;
  roots: Root[];
  modalities: { modality: string; count: number }[];
  profiles: { id: string; model: string; modality: string }[];
  failures: { id: number; name: string; status: string; error_code: string }[];
};
export type Health = {
  status: string;
  semantic_ready: boolean;
  text_model: string;
  device: string;
  ocr_enabled: boolean;
  vision_enabled: boolean;
  media_enabled: boolean;
  model_setup_command?: string;
};
export type Job = {
  id: string;
  state: string;
  total: number;
  processed: number;
  indexed: number;
  skipped: number;
  failed: number;
  deleted: number;
  created_at: string;
  errors?: { relative_path: string; code: string; message: string }[];
};
export type FileDetail = {
  id: number;
  name: string;
  path: string;
  modality: string;
  source_available: boolean;
  source_error?: string;
  warnings: string[];
  chunks: {
    id: number;
    text: string;
    kind: string;
    asset: string | null;
    locator: Locator;
  }[];
};
export type SearchResponse = {
  query: string;
  results: Result[];
  latency_ms: number;
  mode: string;
  warnings: string[];
};
export type AnswerResponse = {
  answer: string;
  citations: (Evidence & {
    id: string;
    file_id: number;
    name: string;
    relative_path: string;
  })[];
  supported: boolean | null;
  notice?: string;
  retrieval: SearchResponse;
};
