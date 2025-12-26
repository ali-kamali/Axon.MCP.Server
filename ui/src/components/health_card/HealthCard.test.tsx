import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import HealthCard from "./HealthCard";

describe("HealthCard", () => {
  it("renders service name", () => {
    render(
      <HealthCard
        status="healthy"
        service="Axon MCP Server"
        version="1.0.0"
        environment="development"
      />
    );

    expect(screen.getByText("Axon MCP Server")).toBeInTheDocument();
  });

  it("renders status information", () => {
    render(
      <HealthCard
        status="healthy"
        service="Test Service"
        version="1.0.0"
        environment="development"
      />
    );

    expect(screen.getByText("Status")).toBeInTheDocument();
    expect(screen.getByText("healthy")).toBeInTheDocument();
  });

  it("renders environment information", () => {
    render(
      <HealthCard
        status="healthy"
        service="Test Service"
        version="1.0.0"
        environment="production"
      />
    );

    expect(screen.getByText("Environment")).toBeInTheDocument();
    expect(screen.getByText("production")).toBeInTheDocument();
  });

  it("renders version information", () => {
    render(
      <HealthCard
        status="healthy"
        service="Test Service"
        version="2.5.1"
        environment="staging"
      />
    );

    expect(screen.getByText("Version")).toBeInTheDocument();
    expect(screen.getByText("2.5.1")).toBeInTheDocument();
  });

  it("renders all props correctly", () => {
    const props = {
      status: "operational",
      service: "My Service",
      version: "3.0.0",
      environment: "staging",
    };

    render(<HealthCard {...props} />);

    expect(screen.getByText(props.service)).toBeInTheDocument();
    expect(screen.getByText(props.status)).toBeInTheDocument();
    expect(screen.getByText(props.version)).toBeInTheDocument();
    expect(screen.getByText(props.environment)).toBeInTheDocument();
  });
});

