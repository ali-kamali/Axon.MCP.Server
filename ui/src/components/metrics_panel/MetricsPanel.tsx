import { useMemo } from "react";

import styles from "./MetricsPanel.module.css";

export type MetricsPanelProps = {
  metrics_text?: string;
};

type MetricSample = {
  name: string;
  labels: Record<string, string>;
  value: number;
};

type BreakdownItem = {
  key: string;
  value: number;
  percentage: number;
};

type BreakdownSummary = {
  total: number;
  items: BreakdownItem[];
};

const METRIC_LINE_REGEX = /^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{([^}]*)\})?\s+([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)/;
const LABEL_REGEX = /(\w+)="([^"]*)"/g;

const compactNumberFormatter = Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
});

function parseMetrics(text: string | undefined): MetricSample[] {
  if (!text) {
    return [];
  }

  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0 && !line.startsWith("#"))
    .map((line) => {
      const match = METRIC_LINE_REGEX.exec(line);
      if (!match) {
        return null;
      }

      const [, name, labelBlock] = match;
      const value = Number.parseFloat(match[4]);
      if (Number.isNaN(value)) {
        return null;
      }

      const labels: Record<string, string> = {};
      if (labelBlock) {
        let labelMatch: RegExpExecArray | null;
        while ((labelMatch = LABEL_REGEX.exec(labelBlock)) !== null) {
          labels[labelMatch[1]] = labelMatch[2];
        }
        LABEL_REGEX.lastIndex = 0;
      }

      return { name, labels, value } satisfies MetricSample;
    })
    .filter((entry): entry is MetricSample => entry !== null);
}

function sumMetric(samples: MetricSample[], metricName: string, predicate?: (labels: Record<string, string>) => boolean): number {
  return samples
    .filter((sample) => sample.name === metricName && (!predicate || predicate(sample.labels)))
    .reduce((acc, sample) => acc + sample.value, 0);
}

function buildBreakdown(
  samples: MetricSample[],
  metricName: string,
  labelKey: string
): BreakdownSummary | null {
  const relevant = samples.filter((sample) => sample.name === metricName && sample.labels[labelKey]);
  if (relevant.length === 0) {
    return null;
  }

  const totals = new Map<string, number>();
  for (const sample of relevant) {
    const key = sample.labels[labelKey] ?? "unknown";
    const current = totals.get(key) ?? 0;
    totals.set(key, current + sample.value);
  }

  const totalValue = Array.from(totals.values()).reduce((acc, value) => acc + value, 0);
  if (totalValue === 0) {
    return {
      total: 0,
      items: Array.from(totals.entries()).map(([key]) => ({ key, value: 0, percentage: 0 })),
    } satisfies BreakdownSummary;
  }

  const items = Array.from(totals.entries())
    .map(([key, value]) => ({
      key,
      value,
      percentage: value / totalValue,
    }))
    .sort((a, b) => b.value - a.value);

  return {
    total: totalValue,
    items,
  } satisfies BreakdownSummary;
}

function formatBytes(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return "—";
  }

  if (value < 1024) {
    return `${value.toFixed(0)} B`;
  }

  const units = ["KB", "MB", "GB", "TB"];
  let unitIndex = -1;
  let remainder = value;
  while (remainder >= 1024 && unitIndex < units.length - 1) {
    remainder /= 1024;
    unitIndex += 1;
  }

  return `${remainder.toFixed(remainder < 10 ? 1 : 0)} ${units[unitIndex]}`;
}

function formatPercent(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return "—";
  }
  return `${value.toFixed(1)}%`;
}

function formatCompact(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return "—";
  }
  return compactNumberFormatter.format(value);
}

function renderBreakdown(summary: BreakdownSummary | null, label: string) {
  if (!summary) {
    return (
      <div className={styles.breakdown_card} key={label}>
        <h3 className={styles.breakdown_title}>{label}</h3>
        <p className={styles.breakdown_hint}>No data available.</p>
      </div>
    );
  }

  return (
    <div className={styles.breakdown_card} key={label}>
      <div className={styles.breakdown_header}>
        <h3 className={styles.breakdown_title}>{label}</h3>
        <span className={styles.breakdown_total}>{formatCompact(summary.total)}</span>
      </div>
      <ul className={styles.breakdown_list}>
        {summary.items.map((item) => (
          <li key={item.key} className={styles.breakdown_item}>
            <span className={styles.breakdown_key}>{item.key}</span>
            <span className={styles.breakdown_value}>{formatCompact(item.value)}</span>
            <span className={styles.breakdown_percentage}>{formatPercent(item.percentage * 100)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function MetricsPanel({ metrics_text }: MetricsPanelProps) {
  const samples = useMemo(() => parseMetrics(metrics_text), [metrics_text]);

  const highlightCards = useMemo(() => {
    const cards: Array<{ id: string; label: string; value: string; hint: string }> = [];

    const activeWorkers = samples.find((sample) => sample.name === "active_workers");
    if (activeWorkers) {
      cards.push({
        id: "active_workers",
        label: "Active Workers",
        value: formatCompact(activeWorkers.value),
        hint: "Celery fleet",
      });
    }

    const cpuUsage = samples.find((sample) => sample.name === "cpu_usage_percent");
    if (cpuUsage) {
      cards.push({
        id: "cpu_usage",
        label: "CPU Utilisation",
        value: formatPercent(cpuUsage.value),
        hint: "Process average",
      });
    }

    const memoryUsage = samples.find((sample) => sample.name === "memory_usage_bytes");
    if (memoryUsage) {
      cards.push({
        id: "memory_usage",
        label: "Memory Usage",
        value: formatBytes(memoryUsage.value),
        hint: "Resident",
      });
    }

    const apiRequests = sumMetric(samples, "api_requests_total");
    if (apiRequests > 0) {
      cards.push({
        id: "api_requests",
        label: "API Requests",
        value: formatCompact(apiRequests),
        hint: "All routes",
      });
    }

    const searchQueries = sumMetric(samples, "search_queries_total");
    if (searchQueries > 0) {
      cards.push({
        id: "search_queries",
        label: "Search Queries",
        value: formatCompact(searchQueries),
        hint: "Indexed search",
      });
    }

    const syncDurationSum = sumMetric(samples, "repository_sync_duration_seconds_sum");
    const syncDurationCount = sumMetric(samples, "repository_sync_duration_seconds_count");
    if (syncDurationSum > 0 && syncDurationCount > 0) {
      const averageRepoSyncDuration = syncDurationSum / syncDurationCount;
      cards.push({
        id: "sync_duration",
        label: "Avg Sync Duration",
        value: `${averageRepoSyncDuration.toFixed(1)}s`,
        hint: "Last window",
      });
    }

    return cards;
  }, [samples]);

  const repositorySyncBreakdown = useMemo(
    () => buildBreakdown(samples, "repository_sync_total", "status"),
    [samples]
  );

  const searchBreakdown = useMemo(
    () => buildBreakdown(samples, "search_queries_total", "status"),
    [samples]
  );

  const taskBreakdown = useMemo(
    () => buildBreakdown(samples, "celery_tasks_total", "status"),
    [samples]
  );

  const parsingBreakdown = useMemo(
    () => buildBreakdown(samples, "files_parsed_total", "status"),
    [samples]
  );

  const hasMetrics = samples.length > 0;

  return (
    <section className={styles.metrics_container}>
      <div className={styles.metrics_header}>
        <h2 className={styles.metrics_title}>Operational Metrics</h2>
        <span className={styles.metrics_caption}>
          {hasMetrics ? "Prometheus snapshot" : "No metrics captured"}
        </span>
      </div>

      {hasMetrics ? (
        <div className={styles.metrics_content}>
          {highlightCards.length > 0 && (
            <div className={styles.highlight_grid}>
              {highlightCards.map((card) => (
                <article key={card.id} className={styles.highlight_card}>
                  <span className={styles.highlight_label}>{card.label}</span>
                  <span className={styles.highlight_value}>{card.value}</span>
                  <span className={styles.highlight_hint}>{card.hint}</span>
                </article>
              ))}
            </div>
          )}

          <div className={styles.breakdown_grid}>
            {renderBreakdown(repositorySyncBreakdown, "Repository Syncs")}
            {renderBreakdown(searchBreakdown, "Search Queries")}
            {renderBreakdown(taskBreakdown, "Celery Tasks")}
            {renderBreakdown(parsingBreakdown, "Files Parsed")}
          </div>

          <details className={styles.raw_section}>
            <summary className={styles.raw_summary}>View raw Prometheus metrics</summary>
            <pre className={styles.raw_pre}>{metrics_text}</pre>
          </details>
        </div>
      ) : (
        <div className={styles.metrics_empty_state}>
          <p className={styles.metrics_hint}>
            Metrics endpoint returned no samples. Confirm Prometheus scraping is enabled for the server.
          </p>
        </div>
      )}
    </section>
  );
}

