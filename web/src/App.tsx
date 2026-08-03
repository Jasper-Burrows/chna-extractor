import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createDemoExtraction,
  createExtraction,
  downloadExport,
  getConfig,
  getEvents,
  getJob,
  getResult,
  triggerDownload,
  updateResult,
} from "./lib/api";
import { formatBytes } from "./lib/format";
import type { ExtractionJob, ExtractionMode, ExtractionResult, HospitalRecord } from "./types";
import { Icon } from "./components/Icon";
import { ModeBadge } from "./components/ModeBadge";
import { ProgressPanel } from "./components/ProgressPanel";
import { ResultWorkspace } from "./components/ResultWorkspace";
import { UploadPanel } from "./components/UploadPanel";

type Submission = { type: "demo" } | { type: "file"; file: File; mode: ExtractionMode };

function messageFromError(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "Something went wrong. Please try again.";
}

export function App() {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<ExtractionMode>("auto");
  const [jobId, setJobId] = useState<string | null>(null);
  const [initialJob, setInitialJob] = useState<ExtractionJob | null>(null);
  const [editableResult, setEditableResult] = useState<ExtractionResult | null>(null);
  const [dirty, setDirty] = useState(false);
  const [localError, setLocalError] = useState("");
  const [saveMessage, setSaveMessage] = useState("");

  const configQuery = useQuery({
    queryKey: ["config"],
    queryFn: getConfig,
    staleTime: 30_000,
    retry: 1,
    refetchInterval: 60_000,
  });

  const submitMutation = useMutation({
    mutationFn: (submission: Submission) => submission.type === "demo"
      ? createDemoExtraction()
      : createExtraction(submission.file, submission.mode),
    onSuccess: (job) => {
      setInitialJob(job);
      setJobId(job.id);
      setEditableResult(null);
      setDirty(false);
      setLocalError("");
      setSaveMessage("");
      window.scrollTo({ top: 0, behavior: "smooth" });
    },
  });

  const jobQuery = useQuery({
    queryKey: ["extraction", jobId],
    queryFn: () => getJob(jobId as string),
    enabled: Boolean(jobId),
    initialData: initialJob ?? undefined,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "succeeded" || status === "failed" ? false : 700;
    },
  });

  const job = jobQuery.data ?? initialJob;
  const terminal = job?.status === "succeeded" || job?.status === "failed";

  const eventsQuery = useQuery({
    queryKey: ["events", jobId],
    queryFn: () => getEvents(jobId as string),
    enabled: Boolean(jobId),
    refetchInterval: terminal ? false : 900,
  });

  const resultQuery = useQuery({
    queryKey: ["result", jobId],
    queryFn: () => getResult(jobId as string),
    enabled: Boolean(jobId && job?.status === "succeeded"),
    staleTime: Infinity,
  });

  const saveMutation = useMutation({
    mutationFn: (result: ExtractionResult) => updateResult(result.job_id, result),
    onSuccess: (saved) => {
      setEditableResult(saved);
      setDirty(false);
      setSaveMessage("Review saved just now");
      queryClient.setQueryData(["result", saved.job_id], saved);
    },
  });

  const exportMutation = useMutation({
    mutationFn: async ({ format, result }: { format: "json" | "csv"; result: ExtractionResult }) => {
      let exportable = result;
      if (dirty) exportable = await updateResult(result.job_id, result);
      const blob = await downloadExport(result.job_id, format);
      return { blob, format, result: exportable };
    },
    onSuccess: ({ blob, format, result }) => {
      setEditableResult(result);
      setDirty(false);
      setSaveMessage("Review saved and export prepared");
      const stem = result.source_file.replace(/\.pdf$/i, "").replace(/[^a-z0-9_-]+/gi, "-").toLowerCase();
      triggerDownload(blob, `${stem || "chna-extraction"}.${format}`);
    },
  });

  const submissionError = localError
    || (submitMutation.error ? messageFromError(submitMutation.error) : "")
    || (jobQuery.error ? messageFromError(jobQuery.error) : "");
  const saveError = saveMutation.error
    ? messageFromError(saveMutation.error)
    : exportMutation.error
      ? messageFromError(exportMutation.error)
      : "";

  const validateAndSubmit = (file: File) => {
    const maxMb = configQuery.data?.max_upload_mb ?? 20;
    setLocalError("");
    if (!file.name.toLowerCase().endsWith(".pdf") || (file.type && file.type !== "application/pdf")) {
      setLocalError("Choose a PDF report. Other file types are not accepted.");
      return;
    }
    if (file.size === 0) {
      setLocalError("This PDF is empty. Choose a report with readable pages.");
      return;
    }
    if (file.size > maxMb * 1024 * 1024) {
      setLocalError(`This file is ${formatBytes(file.size)}. The secure upload limit is ${maxMb} MB.`);
      return;
    }
    submitMutation.mutate({ type: "file", file, mode });
  };

  const reset = () => {
    if (jobId) {
      queryClient.removeQueries({ queryKey: ["extraction", jobId] });
      queryClient.removeQueries({ queryKey: ["events", jobId] });
      queryClient.removeQueries({ queryKey: ["result", jobId] });
    }
    setJobId(null);
    setInitialJob(null);
    setEditableResult(null);
    setDirty(false);
    setLocalError("");
    setSaveMessage("");
    submitMutation.reset();
  };

  const updateRecord = (index: number, record: HospitalRecord) => {
    setEditableResult((current) => {
      const base = current ?? resultQuery.data;
      return base ? {
        ...base,
        records: base.records.map((item, itemIndex) => itemIndex === index ? record : item),
      } : current;
    });
    setDirty(true);
    setSaveMessage("");
  };

  const isWorking = submitMutation.isPending || Boolean(job && !terminal);
  const displayedResult = editableResult ?? resultQuery.data ?? null;
  const view = displayedResult ? "result" : job ? "progress" : "upload";

  return (
    <div className="app-shell">
      <header className="site-header">
        <div className="header-inner">
          <a className="brand" href="/" aria-label="CHNA Lens home">
            <span className="brand-mark"><Icon name="hospital" size={23} /></span>
            <span><strong>CHNA</strong> Lens</span>
          </a>
          <nav aria-label="Primary navigation">
            <a href="#how-it-works">How it works</a>
            <a href="/docs" target="_blank" rel="noreferrer">API docs <Icon name="external" size={14} /></a>
          </nav>
          <ModeBadge config={configQuery.data} mode={mode} />
        </div>
      </header>

      <main id="main-content">
        <div className="hero-copy">
          <span className="hero-kicker"><Icon name="sparkle" size={15} /> Evidence-first document intelligence</span>
          <h1>Turn a health report into<br /><em>decisions you can verify.</em></h1>
          <p>Extract hospital details, community priorities, and methodologies from CHNA PDFs—with page-level evidence attached.</p>
        </div>

        <div className={`workflow-layout workflow-layout--${view}`}>
          <div className="workflow-main">
            {view === "upload" && (
              <UploadPanel
                config={configQuery.data}
                mode={mode}
                busy={isWorking}
                error={submissionError}
                onModeChange={setMode}
                onUpload={validateAndSubmit}
                onDemo={() => submitMutation.mutate({ type: "demo" })}
              />
            )}
            {view === "progress" && job && (
              <ProgressPanel job={job} events={eventsQuery.data?.items ?? []} onReset={reset} />
            )}
            {view === "result" && displayedResult && (
              <ResultWorkspace
                result={displayedResult}
                dirty={dirty}
                saving={saveMutation.isPending || exportMutation.isPending}
                saveMessage={saveError || saveMessage}
                onChange={updateRecord}
                onSave={() => saveMutation.mutate(displayedResult)}
                onDownload={(format) => exportMutation.mutate({ format, result: displayedResult })}
                onNew={reset}
              />
            )}
          </div>

          {view !== "result" && (
            <aside className="trust-panel" aria-labelledby="trust-title">
              <div className="trust-visual" aria-hidden="true">
                <div className="paper-stack paper-stack--back" />
                <div className="paper-stack paper-stack--mid" />
                <div className="document-preview">
                  <div className="preview-top"><span /><span /></div>
                  <div className="preview-title" /><div className="preview-line preview-line--long" />
                  <div className="preview-line" /><div className="preview-line preview-line--short" />
                  <div className="highlight-box"><span /><div><b /><i /></div><small>94%</small></div>
                  <div className="preview-line preview-line--long" />
                  <div className="preview-line" />
                </div>
                <div className="verified-pill"><Icon name="check" size={15} /> Source verified</div>
              </div>
              <span className="eyebrow">Built for review</span>
              <h2 id="trust-title">Reliable by design,<br />transparent by default.</h2>
              <ul>
                <li><span><Icon name="search" size={18} /></span><div><strong>Trace every answer</strong><p>Evidence excerpts and page numbers stay beside each field.</p></div></li>
                <li><span><Icon name="edit" size={18} /></span><div><strong>Keep a human in control</strong><p>Review and correct results before anything is exported.</p></div></li>
                <li><span><Icon name="shield" size={18} /></span><div><strong>Demo privately</strong><p>Try a deterministic sample without sending data to an AI provider.</p></div></li>
              </ul>
            </aside>
          )}
        </div>

        <section className="how-it-works" id="how-it-works" aria-labelledby="steps-title">
          <div><span className="eyebrow">Simple workflow</span><h2 id="steps-title">From PDF to verified data</h2></div>
          <ol>
            <li><span>01</span><div><strong>Upload</strong><p>Add one CHNA report or use the synthetic demo.</p></div></li>
            <li><span>02</span><div><strong>Extract</strong><p>Structured fields and citations are gathered together.</p></div></li>
            <li><span>03</span><div><strong>Review</strong><p>Inspect confidence and edit the record in place.</p></div></li>
            <li><span>04</span><div><strong>Export</strong><p>Download canonical JSON or compatible CSV.</p></div></li>
          </ol>
        </section>
      </main>

      <footer>
        <div><span className="brand brand--footer"><span className="brand-mark"><Icon name="hospital" size={18} /></span><span><strong>CHNA</strong> Lens</span></span><p>A public portfolio project for accountable health-data extraction.</p></div>
        <p>Built with synthetic examples · No employer data included</p>
      </footer>
    </div>
  );
}
