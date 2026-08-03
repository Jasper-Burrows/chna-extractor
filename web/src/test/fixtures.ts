import type { AppConfig, ExtractionJob, ExtractionResult } from "../types";

export const configFixture: AppConfig = {
  offline_demo_available: true,
  live_available: false,
  max_upload_mb: 20,
  model: "gpt-5.6-terra",
};

export const jobFixture: ExtractionJob = {
  id: "demo-job-001",
  status: "succeeded",
  progress: 100,
  message: "Extraction complete",
  mode: "offline",
  source_filename: "synthetic_chna.pdf",
  created_at: "2026-08-03T02:00:00Z",
  updated_at: "2026-08-03T02:00:01Z",
  links: {},
};

export const resultFixture: ExtractionResult = {
  job_id: jobFixture.id,
  source_file: jobFixture.source_filename,
  completed_at: "2026-08-03T02:00:01Z",
  usage: { latency_ms: 1, estimated_cost_usd: 0, total_tokens: 0, model: "deterministic-demo" },
  warnings: [{
    code: "offline_demo",
    message: "Deterministic output from the bundled synthetic fixture; no AI service was called.",
    severity: "info",
  }],
  records: [
    {
      hospital_name: "Example County Community Hospital",
      hospital_system: "Civic Health Collaborative (Synthetic)",
      report_year: 2025,
      address: "100 Example Way",
      city: "Demo City",
      state: "CA",
      postal_code: "90000",
      latitude: null,
      longitude: null,
      capacity: 128,
      urban_rural: "urban",
      health_priorities: ["Access to primary care", "Behavioral health", "Nutrition and physical activity"],
      assessment_methodologies: ["Community survey", "Stakeholder interviews", "Secondary data review"],
      warnings: [],
      evidence: {
        hospital_name: [{ page: 1, excerpt: "Example County Community Hospital", confidence: 1, method: "document_text" }],
        hospital_system: [{ page: 1, excerpt: "Civic Health Collaborative (Synthetic)", confidence: 1, method: "document_text" }],
        report_year: [{ page: 1, excerpt: "2025 Community Health Needs Assessment", confidence: 1, method: "document_text" }],
        address: [{ page: 1, excerpt: "Address: 100 Example Way, Demo City, CA 90000", confidence: 1, method: "document_text" }],
        capacity: [{ page: 1, excerpt: "Licensed bed capacity: 128", confidence: 1, method: "document_text" }],
        urban_rural: [{ page: 1, excerpt: "Service area classification: Urban", confidence: 1, method: "document_text" }],
        health_priorities: [{ page: 1, excerpt: "Priorities: Access to primary care; Behavioral health; Nutrition and physical activity", confidence: 1, method: "document_text" }],
        assessment_methodologies: [{ page: 1, excerpt: "Methods: Community survey; Stakeholder interviews; Secondary data review", confidence: 1, method: "document_text" }],
      },
    },
  ],
};
