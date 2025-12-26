import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import SearchResultsTable from "./SearchResultsTable";
import { LanguageEnum, SymbolKindEnum } from "../../types/enums";
import type { SearchResult } from "../../services/api";

describe("SearchResultsTable", () => {
  const baseResult: SearchResult = {
    symbol_id: 1,
    file_id: 10,
    repository_id: 42,
    repository_name: "example-repo",
    file_path: "src/index.ts",
    language: LanguageEnum.typescript,
    kind: SymbolKindEnum.function,
    name: "doSomething",
    fully_qualified_name: "Example.Namespace.doSomething",
    start_line: 5,
    end_line: 25,
    score: 0.87,
    updated_at: new Date().toISOString(),
  };

  it("renders empty state when no results provided", () => {
    render(<SearchResultsTable results={[]} />);

    expect(screen.getByText(/No results yet/i)).toBeInTheDocument();
  });

  it("renders rows and triggers detail callback", () => {
    const handleSelect = vi.fn();
    render(<SearchResultsTable results={[baseResult]} on_select_symbol={handleSelect} />);

    expect(screen.getByText(baseResult.name)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /view details/i }));
    expect(handleSelect).toHaveBeenCalledWith(baseResult);
  });
});


