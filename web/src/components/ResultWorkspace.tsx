import { useState } from "react";
import type { ReactNode } from "react";
import { allWarnings, confidenceFor, confidenceLabel, formatCost, formatDuration, friendlyField, getEvidence } from "../lib/format";
import type { ExtractionResult, FieldEvidence, HospitalRecord } from "../types";
import { Icon } from "./Icon";

type EditableField = Exclude<keyof HospitalRecord, "evidence" | "warnings">;

interface ResultWorkspaceProps {
  result: ExtractionResult;
  dirty: boolean;
  saving: boolean;
  saveMessage: string;
  onChange: (index: number, record: HospitalRecord) => void;
  onSave: () => void;
  onDownload: (format: "json" | "csv") => void;
  onNew: () => void;
}

interface FieldShellProps {
  label: string;
  field: EditableField;
  inputId: string;
  evidence: FieldEvidence[];
  wide?: boolean;
  children: ReactNode;
}

function ConfidenceBadge({ evidence }: { evidence: FieldEvidence[] }) {
  const confidence = confidenceFor(evidence);
  const level = confidenceLabel(confidence);
  if (confidence === null) return <span className="confidence confidence--none">No citation</span>;
  return (
    <span className={`confidence confidence--${level}`}>
      <span aria-hidden="true" /> {Math.round(confidence * 100)}% confidence
    </span>
  );
}

function safeSourceUrl(value?: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

function EvidenceDisclosure({ field, evidence }: { field: string; evidence: FieldEvidence[] }) {
  if (!evidence.length) return null;
  return (
    <details className="evidence-disclosure">
      <summary><Icon name="search" size={15} /> View {evidence.length > 1 ? `${evidence.length} sources` : "source"}</summary>
      <div className="evidence-list">
        {evidence.map((item, index) => {
          const sourceUrl = safeSourceUrl(item.source_url);
          return (
            <blockquote key={`${item.page}-${index}`}>
              <p>“{item.excerpt}”</p>
              <footer>
                {item.method === "user_edit" ? "Human review" : item.page ? `Page ${item.page}` : "External evidence"}
                <span aria-hidden="true">·</span>
                {item.method || "text extraction"}
                {sourceUrl && <><span aria-hidden="true">·</span><a href={sourceUrl} target="_blank" rel="noreferrer">{item.source_title || "Open source"}<Icon name="external" size={11} /></a></>}
              </footer>
            </blockquote>
          );
        })}
      </div>
      <span className="visually-hidden">Evidence for {friendlyField(field)}</span>
    </details>
  );
}

function FieldShell({ label, field, inputId, evidence, wide, children }: FieldShellProps) {
  return (
    <div className={`editor-field ${wide ? "editor-field--wide" : ""}`}>
      <div className="editor-field__heading">
        <label htmlFor={inputId}>{label}</label>
        <ConfidenceBadge evidence={evidence} />
      </div>
      {children}
      <EvidenceDisclosure field={field} evidence={evidence} />
    </div>
  );
}

function cleanNumber(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function RecordEditor({ record, index, onChange }: { record: HospitalRecord; index: number; onChange: (record: HospitalRecord) => void }) {
  const update = <K extends EditableField>(field: K, value: HospitalRecord[K]) => {
    onChange({ ...record, [field]: value });
  };
  const id = (field: string) => `record-${index}-${field}`;

  return (
    <div className="record-editor">
      <section className="editor-section" aria-labelledby={`identity-${index}`}>
        <div className="editor-section__title">
          <span className="section-icon"><Icon name="hospital" size={19} /></span>
          <div><h3 id={`identity-${index}`}>Hospital identity</h3><p>Core organization and reporting details</p></div>
        </div>
        <div className="editor-grid">
          <FieldShell label="Hospital name" field="hospital_name" inputId={id("hospital_name")} evidence={getEvidence(record, "hospital_name")} wide>
            <input id={id("hospital_name")} value={record.hospital_name ?? ""} onChange={(event) => update("hospital_name", event.target.value || null)} />
          </FieldShell>
          <FieldShell label="Health system" field="hospital_system" inputId={id("hospital_system")} evidence={getEvidence(record, "hospital_system")}>
            <input id={id("hospital_system")} value={record.hospital_system ?? ""} onChange={(event) => update("hospital_system", event.target.value || null)} />
          </FieldShell>
          <FieldShell label="Report year" field="report_year" inputId={id("report_year")} evidence={getEvidence(record, "report_year")}>
            <input id={id("report_year")} inputMode="numeric" min="1990" max="2100" type="number" value={record.report_year ?? ""} onChange={(event) => update("report_year", cleanNumber(event.target.value))} />
          </FieldShell>
          <FieldShell label="Licensed capacity" field="capacity" inputId={id("capacity")} evidence={getEvidence(record, "capacity")}>
            <div className="input-suffix"><input id={id("capacity")} inputMode="numeric" min="0" type="number" value={record.capacity ?? ""} onChange={(event) => update("capacity", cleanNumber(event.target.value))} /><span>beds</span></div>
          </FieldShell>
          <FieldShell label="Community setting" field="urban_rural" inputId={id("urban_rural")} evidence={getEvidence(record, "urban_rural")}>
            <select id={id("urban_rural")} value={record.urban_rural ?? "unknown"} onChange={(event) => update("urban_rural", event.target.value as HospitalRecord["urban_rural"])}>
              <option value="unknown">Unknown</option><option value="urban">Urban</option><option value="rural">Rural</option><option value="suburban">Suburban</option>
            </select>
          </FieldShell>
        </div>
      </section>

      <section className="editor-section" aria-labelledby={`location-${index}`}>
        <div className="editor-section__title">
          <span className="section-icon section-icon--mint"><Icon name="location" size={19} /></span>
          <div><h3 id={`location-${index}`}>Location</h3><p>Normalized site address from the report</p></div>
        </div>
        <div className="editor-grid editor-grid--location">
          <FieldShell label="Street address" field="address" inputId={id("address")} evidence={getEvidence(record, "address")} wide>
            <input id={id("address")} autoComplete="street-address" value={record.address ?? ""} onChange={(event) => update("address", event.target.value || null)} />
          </FieldShell>
          <FieldShell label="City" field="city" inputId={id("city")} evidence={getEvidence(record, "city")}>
            <input id={id("city")} autoComplete="address-level2" value={record.city ?? ""} onChange={(event) => update("city", event.target.value || null)} />
          </FieldShell>
          <FieldShell label="State" field="state" inputId={id("state")} evidence={getEvidence(record, "state")}>
            <input id={id("state")} autoComplete="address-level1" maxLength={30} value={record.state ?? ""} onChange={(event) => update("state", event.target.value || null)} />
          </FieldShell>
          <FieldShell label="Postal code" field="postal_code" inputId={id("postal_code")} evidence={getEvidence(record, "postal_code")}>
            <input id={id("postal_code")} autoComplete="postal-code" value={record.postal_code ?? ""} onChange={(event) => update("postal_code", event.target.value || null)} />
          </FieldShell>
        </div>
      </section>

      <section className="editor-section" aria-labelledby={`community-${index}`}>
        <div className="editor-section__title">
          <span className="section-icon section-icon--orange"><Icon name="sparkle" size={19} /></span>
          <div><h3 id={`community-${index}`}>Community findings</h3><p>One item per line; edit anything that needs correction</p></div>
        </div>
        <div className="editor-grid">
          <FieldShell label="Health priorities" field="health_priorities" inputId={id("health_priorities")} evidence={getEvidence(record, "health_priorities")} wide>
            <textarea id={id("health_priorities")} rows={5} value={record.health_priorities.join("\n")} onChange={(event) => update("health_priorities", event.target.value.split("\n").map((item) => item.trim()).filter(Boolean))} />
          </FieldShell>
          <FieldShell label="Assessment methodologies" field="assessment_methodologies" inputId={id("assessment_methodologies")} evidence={getEvidence(record, "assessment_methodologies")} wide>
            <textarea id={id("assessment_methodologies")} rows={5} value={record.assessment_methodologies.join("\n")} onChange={(event) => update("assessment_methodologies", event.target.value.split("\n").map((item) => item.trim()).filter(Boolean))} />
          </FieldShell>
        </div>
      </section>
    </div>
  );
}

export function ResultWorkspace({ result, dirty, saving, saveMessage, onChange, onSave, onDownload, onNew }: ResultWorkspaceProps) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [showWarnings, setShowWarnings] = useState(true);
  const record = result.records[activeIndex];
  const warnings = record ? allWarnings(record, result.warnings) : result.warnings;
  const evidenceCount = record ? Object.values(record.evidence).reduce((sum, items) => sum + items.length, 0) : 0;

  if (!record) {
    return (
      <section className="empty-result" role="status">
        <Icon name="search" size={30} />
        <h2>No hospital records found</h2>
        <p>The extraction completed, but there was not enough evidence to create a record.</p>
        <button className="primary-button" type="button" onClick={onNew}>Try another report</button>
      </section>
    );
  }

  return (
    <section className="results" aria-labelledby="results-title">
      <div className="results-hero">
        <div>
          <span className="success-kicker"><Icon name="check" size={14} /> Extraction complete</span>
          <h2 id="results-title">Review the findings</h2>
          <p>Every value remains editable. Open a source to verify it against the report.</p>
        </div>
        <button className="secondary-button" type="button" onClick={onNew}><Icon name="refresh" size={17} /> New report</button>
      </div>

      <div className="result-summary" aria-label="Extraction summary">
        <div><span>Hospitals</span><strong>{result.records.length}</strong></div>
        <div><span>Evidence points</span><strong>{evidenceCount}</strong></div>
        <div><span>Processing time</span><strong>{formatDuration(result.usage.latency_ms)}</strong></div>
        <div><span>Estimated AI cost</span><strong>{formatCost(result.usage.estimated_cost_usd)}</strong></div>
      </div>

      {warnings.length > 0 && showWarnings && (
        <div className="review-warning" role="status">
          <span className="warning-icon"><Icon name="warning" size={20} /></span>
          <div>
            <strong>{warnings.length} item{warnings.length === 1 ? "" : "s"} worth a closer look</strong>
            <p>{warnings[0].message}{warnings.length > 1 ? ` + ${warnings.length - 1} more` : ""}</p>
          </div>
          <button type="button" className="icon-button" onClick={() => setShowWarnings(false)} aria-label="Dismiss review warning"><Icon name="x" size={17} /></button>
        </div>
      )}

      {result.records.length > 1 && (
        <div className="record-tabs" role="tablist" aria-label="Hospital records">
          {result.records.map((item, index) => (
            <button key={`${item.hospital_name}-${index}`} role="tab" aria-selected={activeIndex === index} onClick={() => setActiveIndex(index)} type="button">
              <span>{index + 1}</span>{item.hospital_name || `Hospital ${index + 1}`}
            </button>
          ))}
        </div>
      )}

      <RecordEditor record={record} index={activeIndex} onChange={(next) => onChange(activeIndex, next)} />

      <div className="result-actions">
        <div className="save-status" aria-live="polite">
          <Icon name={dirty ? "edit" : "check"} size={17} />
          <span>{saveMessage || (dirty ? "Unsaved review changes" : "Review changes saved")}</span>
        </div>
        <div className="action-buttons">
          <button className="secondary-button" type="button" disabled={saving} onClick={() => onDownload("json")}><Icon name="download" size={17} /> JSON</button>
          <button className="secondary-button" type="button" disabled={saving} onClick={() => onDownload("csv")}><Icon name="download" size={17} /> CSV</button>
          <button className="primary-button" type="button" disabled={!dirty || saving} onClick={onSave}>{saving ? "Saving…" : "Save review"}</button>
        </div>
      </div>
    </section>
  );
}
