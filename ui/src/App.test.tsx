import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import App from "./App";

vi.mock("./pages/dashboard/DashboardPage", () => ({
  default: () => <div>Dashboard content</div>,
}));
vi.mock("./pages/file_browser/FileBrowserPage", () => ({
  default: () => <div>File browser content</div>,
}));
vi.mock("./pages/jobs/JobsPage", () => ({
  default: () => <div>Jobs content</div>,
}));
vi.mock("./pages/repository_detail/RepositoryDetailPage", () => ({
  default: () => <div>Repository detail content</div>,
}));
vi.mock("./pages/repositories/RepositoriesPage", () => ({
  default: () => <div>Repositories content</div>,
}));
vi.mock("./pages/search/SearchPage", () => ({
  default: () => <div>Search content</div>,
}));
vi.mock("./pages/settings/SettingsPage", () => ({
  default: () => <div>Settings content</div>,
}));
vi.mock("./pages/mcp_test/MCPTestPage", () => ({
  default: () => <div>MCP test content</div>,
}));
vi.mock("./pages/login/LoginPage", () => ({
  default: () => <div>Login content</div>,
}));

describe("App routes", () => {
  it("renders dashboard route with lazy-loaded page", async () => {
    render(
      <MemoryRouter
        initialEntries={["/"]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <App />
      </MemoryRouter>
    );

    expect(await screen.findByText("Dashboard content")).toBeInTheDocument();
  });

  it("renders repositories detail route", async () => {
    render(
      <MemoryRouter
        initialEntries={["/repositories/123"]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <App />
      </MemoryRouter>
    );

    expect(await screen.findByText("Repository detail content")).toBeInTheDocument();
  });
});
