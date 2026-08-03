import type {
  AppConfig,
  EventsResponse,
  ExtractionJob,
  ExtractionMode,
  ExtractionResult,
} from "../types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { error?: unknown; detail?: unknown; message?: unknown };
      if (typeof body.error === "string") message = body.error;
      else if (typeof body.detail === "string") message = body.detail;
      else if (typeof body.message === "string") message = body.message;
    } catch {
      // The sanitized status is safer than reflecting an arbitrary server response.
    }
    throw new ApiError(message, response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function getConfig(): Promise<AppConfig> {
  return request<AppConfig>("/api/v1/config");
}

export function createExtraction(file: File, mode: ExtractionMode): Promise<ExtractionJob> {
  const form = new FormData();
  form.append("file", file, file.name);
  form.append("mode", mode);
  return request<ExtractionJob>("/api/v1/extractions", { method: "POST", body: form });
}

export function createDemoExtraction(): Promise<ExtractionJob> {
  return request<ExtractionJob>("/api/v1/extractions/demo", { method: "POST" });
}

export function getJob(id: string): Promise<ExtractionJob> {
  return request<ExtractionJob>(`/api/v1/extractions/${encodeURIComponent(id)}`);
}

export function getEvents(id: string): Promise<EventsResponse> {
  return request<EventsResponse>(`/api/v1/extractions/${encodeURIComponent(id)}/events`);
}

export function getResult(id: string): Promise<ExtractionResult> {
  return request<ExtractionResult>(`/api/v1/extractions/${encodeURIComponent(id)}/result`);
}

export function updateResult(id: string, result: ExtractionResult): Promise<ExtractionResult> {
  const records = result.records.map((record) => ({
    hospital_name: record.hospital_name,
    hospital_system: record.hospital_system,
    report_year: record.report_year,
    address: record.address,
    city: record.city,
    state: record.state,
    postal_code: record.postal_code,
    latitude: record.latitude,
    longitude: record.longitude,
    capacity: record.capacity,
    urban_rural: record.urban_rural,
    health_priorities: record.health_priorities,
    assessment_methodologies: record.assessment_methodologies,
  }));
  return request<ExtractionResult>(`/api/v1/extractions/${encodeURIComponent(id)}/result`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ records }),
  });
}

export async function downloadExport(id: string, format: "json" | "csv"): Promise<Blob> {
  const response = await fetch(
    `${API_BASE}/api/v1/extractions/${encodeURIComponent(id)}/export?format=${format}`,
    { headers: { Accept: format === "json" ? "application/json" : "text/csv" } },
  );
  if (!response.ok) throw new ApiError(`Could not prepare ${format.toUpperCase()} export`, response.status);
  return response.blob();
}

export function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
