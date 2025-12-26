import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import MetricsPanel from "./MetricsPanel";

describe("MetricsPanel", () => {
  it("renders metrics header", () => {
    render(<MetricsPanel />);
    expect(screen.getByText("Metrics")).toBeInTheDocument();
  });

  it("renders default message when no metrics provided", () => {
    render(<MetricsPanel />);
    expect(
      screen.getByText(/No metrics loaded. \(Wire getMetricsRaw in a later task\)/)
    ).toBeInTheDocument();
  });

  it("renders provided metrics text", () => {
    const metricsText = `# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="GET",status="200"} 1234
http_requests_total{method="POST",status="201"} 567`;

    render(<MetricsPanel metrics_text={metricsText} />);
    expect(screen.getByText(/http_requests_total/)).toBeInTheDocument();
  });

  it("renders metrics in pre element", () => {
    const metricsText = "test_metric 42";
    const { container } = render(<MetricsPanel metrics_text={metricsText} />);
    
    const preElement = container.querySelector("pre");
    expect(preElement).toBeInTheDocument();
    expect(preElement).toHaveTextContent("test_metric 42");
  });

  it("handles empty string metrics", () => {
    render(<MetricsPanel metrics_text="" />);
    expect(screen.getByText("Metrics")).toBeInTheDocument();
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

