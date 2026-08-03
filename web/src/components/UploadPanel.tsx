import { useId, useRef, useState } from "react";
import type { DragEvent, KeyboardEvent } from "react";
import type { AppConfig, ExtractionMode } from "../types";
import { Icon } from "./Icon";

interface UploadPanelProps {
  config?: AppConfig;
  mode: ExtractionMode;
  busy: boolean;
  error?: string;
  onModeChange: (mode: ExtractionMode) => void;
  onUpload: (file: File) => void;
  onDemo: () => void;
}

export function UploadPanel({
  config,
  mode,
  busy,
  error,
  onModeChange,
  onUpload,
  onDemo,
}: UploadPanelProps) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const maxMb = config?.max_upload_mb ?? 20;

  const choose = (file?: File) => {
    if (file) onUpload(file);
  };

  const drop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    choose(event.dataTransfer.files[0]);
  };

  const openPicker = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      inputRef.current?.click();
    }
  };

  return (
    <section className="upload-card" aria-labelledby="upload-title">
      <div className="section-heading">
        <div>
          <span className="eyebrow">New extraction</span>
          <h2 id="upload-title">Add a CHNA report</h2>
          <p>We’ll turn the report into structured, reviewable evidence.</p>
        </div>
        <div className="mode-control" aria-label="Extraction mode">
          {(["auto", "offline", "live"] as ExtractionMode[]).map((option) => (
            <button
              className={mode === option ? "active" : ""}
              disabled={busy || (option === "live" && config !== undefined && !config.live_available)}
              key={option}
              onClick={() => onModeChange(option)}
              type="button"
              aria-pressed={mode === option}
              title={option === "live" && !config?.live_available ? "Add an OpenAI key to enable live mode" : undefined}
            >
              {option === "auto" ? "Smart" : option === "offline" ? "Offline" : "Live"}
            </button>
          ))}
        </div>
      </div>

      <input
        ref={inputRef}
        className="visually-hidden"
        id={inputId}
        type="file"
        accept="application/pdf,.pdf"
        aria-label="Choose a CHNA PDF report"
        disabled={busy}
        onChange={(event) => choose(event.target.files?.[0])}
      />
      <div
        className={`drop-zone ${dragging ? "drop-zone--active" : ""} ${busy ? "drop-zone--disabled" : ""}`}
        onClick={() => !busy && inputRef.current?.click()}
        onDragEnter={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragging(false);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDrop={drop}
        onKeyDown={openPicker}
        role="button"
        tabIndex={busy ? -1 : 0}
        aria-describedby={`${inputId}-hint`}
        aria-disabled={busy}
      >
        <span className="drop-zone__icon"><Icon name="upload" size={26} /></span>
        <div>
          <strong>{busy ? "Submitting report…" : "Drop a PDF here"}</strong>
          <span>or <u>browse your computer</u></span>
        </div>
        <small id={`${inputId}-hint`}>PDF only · up to {maxMb} MB · files stay on this server</small>
      </div>

      <div className="demo-row">
        <div className="demo-row__copy">
          <span className="demo-icon"><Icon name="sparkle" size={18} /></span>
          <p><strong>No report handy?</strong><span>Explore a safe synthetic hospital example.</span></p>
        </div>
        <button className="text-button" type="button" onClick={onDemo} disabled={busy || !config?.offline_demo_available}>
          Try sample report <Icon name="arrow" size={17} />
        </button>
      </div>

      {error && (
        <div className="inline-alert inline-alert--error" role="alert">
          <Icon name="warning" size={19} />
          <span>{error}</span>
        </div>
      )}
      <p className="privacy-note"><Icon name="shield" size={16} /> Uploads are validated, size-limited, and never used to train a model.</p>
      <span className="visually-hidden" aria-live="polite">{busy ? "Your extraction is starting" : ""}</span>
    </section>
  );
}
