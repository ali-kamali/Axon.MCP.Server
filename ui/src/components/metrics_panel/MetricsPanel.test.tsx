import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import MetricsPanel from "./MetricsPanel";

describe("MetricsPanel", () => {
  it("renders operational metrics header", () => {
    render(<MetricsPanel />);
    expect(screen.getByRole("heading", { name: "Operational Metrics" })).toBeInTheDocument();
  });

  it("renders empty state message when no metrics provided", () => {
    render(<MetricsPanel />);
    expect(screen.getByText("No metrics captured")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Metrics endpoint returned no samples. Confirm Prometheus scraping is enabled for the server."
      )
    ).toBeInTheDocument();
  });

  it("renders provided metrics text", () => {
    const metricsText = `# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="GET",status="200"} 1234
http_requests_total{method="POST",status="201"} 567`;

    render(<MetricsPanel metrics_text={metricsText} />);
    expect(screen.getByText("Prometheus snapshot")).toBeInTheDocument();
    expect(screen.getByText("View raw Prometheus metrics")).toBeInTheDocument();
    expect(screen.getByText(/http_requests_total/)).toBeInTheDocument();
  });

  it("renders summary cards and breakdowns for known metrics", () => {
    const metricsText = `
active_workers 4
cpu_usage_percent 12.5
memory_usage_bytes 10240
api_requests_total{route="/health"} 100
search_queries_total{status="success"} 10
search_queries_total{status="error"} 2
repository_sync_duration_seconds_sum 25
repository_sync_duration_seconds_count 5
repository_sync_total{status="success"} 3
repository_sync_total{status="failed"} 1
celery_tasks_total{status="ok"} 8
files_parsed_total{status="ok"} 40
`;

    render(<MetricsPanel metrics_text={metricsText} />);

    expect(screen.getByText("Active Workers")).toBeInTheDocument();
    expect(screen.getByText("CPU Utilisation")).toBeInTheDocument();
    expect(screen.getByText("Avg Sync Duration")).toBeInTheDocument();
    expect(screen.getByText("Repository Syncs")).toBeInTheDocument();
    expect(screen.getAllByText("Search Queries").length).toBeGreaterThanOrEqual(1);
  });

  it("handles infinite metric values without crashing", () => {
    const metricsText = `
active_workers +Inf
api_requests_total{route="/a"} 1
`;

    render(<MetricsPanel metrics_text={metricsText} />);
    expect(screen.getByText("∞")).toBeInTheDocument();
    expect(screen.getByText("API Requests")).toBeInTheDocument();
  });

  it("handles empty string metrics", () => {
    render(<MetricsPanel metrics_text="" />);
    expect(screen.getByRole("heading", { name: "Operational Metrics" })).toBeInTheDocument();
  });

  it("handles multiline metrics", () => {
    const metricsText = `metric_one 100
metric_two 200
metric_three 300`;

    render(<MetricsPanel metrics_text={metricsText} />);
    expect(screen.getByText(/metric_one 100/)).toBeInTheDocument();
    expect(screen.getByText(/metric_two 200/)).toBeInTheDocument();
    expect(screen.getByText(/metric_three 300/)).toBeInTheDocument();
  });
});
