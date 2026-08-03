import type { ExtractionWarning, FieldEvidence, HospitalRecord } from "../types";

export function clampProgress(value: number): number {
  const normalized = value <= 1 ? value * 100 : value;
  return Math.min(100, Math.max(0, Math.round(normalized)));
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatCost(value?: number): string {
  if (value === undefined) return "Not applicable";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: value < 0.01 ? 4 : 2,
  }).format(value);
}

export function formatDuration(milliseconds?: number): string {
  if (milliseconds === undefined) return "—";
  if (milliseconds < 1000) return `${Math.round(milliseconds)} ms`;
  return `${(milliseconds / 1000).toFixed(1)} s`;
}

export function getEvidence(record: HospitalRecord, field: keyof HospitalRecord): FieldEvidence[] {
  return record.evidence[String(field)] ?? [];
}

export function confidenceFor(evidence: FieldEvidence[]): number | null {
  if (!evidence.length) return null;
  return evidence.reduce((sum, item) => sum + item.confidence, 0) / evidence.length;
}

export function confidenceLabel(confidence: number | null): "high" | "medium" | "low" | "none" {
  if (confidence === null) return "none";
  if (confidence >= 0.85) return "high";
  if (confidence >= 0.65) return "medium";
  return "low";
}

export function allWarnings(record: HospitalRecord, global: ExtractionWarning[]): ExtractionWarning[] {
  return [...global, ...record.warnings];
}

export function friendlyField(field: string): string {
  return field
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
