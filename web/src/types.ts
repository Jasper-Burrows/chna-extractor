export type ExtractionMode = "auto" | "offline" | "live";
export type JobStatus = "queued" | "running" | "succeeded" | "failed";
export type Confidence = number;

export interface AppConfig {
  offline_demo_available: boolean;
  live_available: boolean;
  max_upload_mb: number;
  model: string;
}

export interface JobLinks {
  self?: string;
  events?: string;
  result?: string;
  export?: string;
}

export interface ExtractionJob {
  id: string;
  status: JobStatus;
  progress: number;
  message: string;
  mode: ExtractionMode;
  source_filename: string;
  created_at: string;
  updated_at: string;
  links: JobLinks;
  error_code?: string | null;
}

export interface ProgressEvent {
  sequence: number;
  stage: string;
  message: string;
  progress: number;
  created_at: string;
}

export interface FieldEvidence {
  page: number | null;
  excerpt: string;
  confidence: Confidence;
  method: string;
  source_url?: string | null;
  source_title?: string | null;
}

export interface ExtractionWarning {
  code?: string;
  message: string;
  field?: string | null;
  severity?: "info" | "warning" | "error";
}

export interface HospitalRecord {
  hospital_name: string | null;
  hospital_system: string | null;
  report_year: number | null;
  address: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  latitude: number | null;
  longitude: number | null;
  capacity: number | null;
  urban_rural: "urban" | "rural" | "suburban" | "unknown" | null;
  health_priorities: string[];
  assessment_methodologies: string[];
  evidence: Record<string, FieldEvidence[]>;
  warnings: ExtractionWarning[];
}

export interface UsageSummary {
  input_tokens?: number;
  cached_input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
  latency_ms?: number;
  estimated_cost_usd?: number;
  model?: string;
}

export interface ExtractionResult {
  job_id: string;
  source_file: string;
  records: HospitalRecord[];
  usage: UsageSummary;
  warnings: ExtractionWarning[];
  completed_at: string;
}

export interface EventsResponse {
  items: ProgressEvent[];
}
