import type { AppConfig, ExtractionMode } from "../types";

interface ModeBadgeProps {
  config?: AppConfig;
  mode?: ExtractionMode;
  compact?: boolean;
}

export function ModeBadge({ config, mode, compact = false }: ModeBadgeProps) {
  const isLive = mode === "live" || (mode === "auto" && config?.live_available);
  const label = isLive ? "Live AI" : "Private demo";
  return (
    <span className={`mode-badge ${isLive ? "mode-badge--live" : "mode-badge--offline"}`}>
      <span className="mode-badge__dot" aria-hidden="true" />
      {compact ? label : `${label} mode`}
    </span>
  );
}
