import { clampProgress } from "../lib/format";
import type { ExtractionJob, ProgressEvent } from "../types";
import { Icon } from "./Icon";
import { ModeBadge } from "./ModeBadge";

interface ProgressPanelProps {
  job: ExtractionJob;
  events: ProgressEvent[];
  onReset: () => void;
}

export function ProgressPanel({ job, events, onReset }: ProgressPanelProps) {
  const percent = clampProgress(job.progress);
  const failed = job.status === "failed";
  const displayedEvents = events.slice(-4);

  return (
    <section className="progress-card" aria-labelledby="progress-title">
      <div className="progress-card__top">
        <div className={`file-tile ${failed ? "file-tile--error" : ""}`}>
          <Icon name={failed ? "warning" : "document"} size={25} />
        </div>
        <div className="progress-card__title">
          <div className="title-row">
            <h2 id="progress-title">{failed ? "Extraction needs attention" : job.source_filename}</h2>
            <ModeBadge mode={job.mode} compact />
          </div>
          <p>{job.message}</p>
        </div>
        <button className="icon-button" type="button" onClick={onReset} aria-label="Close extraction">
          <Icon name="x" size={19} />
        </button>
      </div>

      {!failed && (
        <>
          <div className="progress-meta">
            <span>Processing report</span><strong>{percent}%</strong>
          </div>
          <div
            className="progress-track"
            role="progressbar"
            aria-label="Extraction progress"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={percent}
          >
            <span style={{ width: `${percent}%` }} />
          </div>
          <div className="event-list" aria-live="polite">
            {displayedEvents.length ? displayedEvents.map((event, index) => (
              <div className="event-item" key={event.sequence}>
                <span className={`event-marker ${index === displayedEvents.length - 1 ? "active" : "complete"}`}>
                  {index === displayedEvents.length - 1 ? <span className="pulse-dot" /> : <Icon name="check" size={13} />}
                </span>
                <div><strong>{event.stage.replaceAll("_", " ")}</strong><span>{event.message}</span></div>
              </div>
            )) : (
              <div className="event-item">
                <span className="event-marker active"><span className="pulse-dot" /></span>
                <div><strong>Starting securely</strong><span>Your job has been added to the local queue.</span></div>
              </div>
            )}
          </div>
        </>
      )}

      {failed && (
        <div className="failure-actions">
          <p>Check that the file is a valid PDF. Live extraction also requires a newly issued API key.</p>
          <button className="primary-button" type="button" onClick={onReset}>Choose another report</button>
        </div>
      )}
    </section>
  );
}
