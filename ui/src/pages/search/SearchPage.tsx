import { FormEvent, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import SearchResultsTable from "../../components/search_results/SearchResultsTable";
import {
  getSymbolWithRelations,
  listRepositories,
  searchCode,
  type RepositoryResponse,
  type SearchParams,
  type SearchResult,
  type SymbolWithRelations,
} from "../../services/api";
import { LanguageEnum } from "../../types/enums";
import styles from "./SearchPage.module.css";

type FilterState = {
  query: string;
  repository_id: string;
  language: string;
  limit: number;
};

const initialFilters: FilterState = {
  query: "",
  repository_id: "",
  language: "",
  limit: 20,
};

export default function SearchPage() {
  const [filters, setFilters] = useState<FilterState>(initialFilters);
  const [repositories, setRepositories] = useState<RepositoryResponse[]>([]);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedSymbol, setSelectedSymbol] = useState<SymbolWithRelations | null>(null);
  const [symbolLoading, setSymbolLoading] = useState(false);
  const [searchParams] = useSearchParams();

  useEffect(() => {
    void loadRepositories();
  }, []);

  useEffect(() => {
    const repositoryIdParam = searchParams.get("repository_id");
    const queryParam = searchParams.get("query");

    if (!repositoryIdParam && !queryParam) {
      return;
    }

    setFilters((prev) => ({
      ...prev,
      repository_id: repositoryIdParam ?? prev.repository_id,
      query: queryParam ?? prev.query,
    }));
  }, [searchParams]);

  const [repositoriesLoading, setRepositoriesLoading] = useState(false);

  const loadRepositories = async () => {
    try {
      setRepositoriesLoading(true);
      const data = await listRepositories({ limit: 100 });
      setRepositories(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load repositories");
    } finally {
      setRepositoriesLoading(false);
    }
  };

  const handleInputChange = (field: keyof FilterState, value: string) => {
    if (field === "limit") {
      const numeric = Number(value);
      const sane = Number.isFinite(numeric) && numeric > 0 ? Math.min(Math.floor(numeric), 100) : 20;
      setFilters((prev) => ({ ...prev, limit: sane }));
      return;
    }

    setFilters((prev) => ({ ...prev, [field]: value }));
  };

  const handleSearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!filters.query.trim()) {
      setError("Enter a search query to continue");
      return;
    }

    const params: SearchParams = {
      query: filters.query.trim(),
      limit: filters.limit,
    };

    if (filters.repository_id) {
      params.repository_id = Number(filters.repository_id);
    }

    if (filters.language) {
      params.language = filters.language as LanguageEnum;
    }

    try {
      setLoading(true);
      setError(null);
      const data = await searchCode(params);
      setResults(data);
      setSelectedSymbol(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search request failed");
    } finally {
      setLoading(false);
    }
  };

  const loadSymbolDetails = async (result: SearchResult) => {
    try {
      setSymbolLoading(true);
      const detail = await getSymbolWithRelations(result.symbol_id);
      setSelectedSymbol(detail);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load symbol details");
    } finally {
      setSymbolLoading(false);
    }
  };

  const repositoryOptions = useMemo(() => {
    return repositories.map((repo) => (
      <option key={repo.id} value={repo.id}>
        {repo.name}
      </option>
    ));
  }, [repositories]);

  const languageOptions = Object.values(LanguageEnum).map((value) => (
    <option key={value} value={value}>
      {value.charAt(0) + value.slice(1).toLowerCase().replace(/_/g, " ")}
    </option>
  ));

  return (
    <div className={styles.search_layout}>
      <section className={styles.search_panel}>
        <div>
          <h1 className={styles.search_title}>Code Search</h1>
          <p className={styles.search_subtitle}>Query indexed repositories and inspect symbol metadata.</p>
        </div>

        <form className={styles.search_form} onSubmit={handleSearch}>
          <div className={styles.form_group}>
            <label className={styles.form_label} htmlFor="search_query">
              Query
            </label>
            <input
              id="search_query"
              className={styles.form_input}
              value={filters.query}
              onChange={(event) => handleInputChange("query", event.target.value)}
              placeholder="Search symbols or files"
              required
            />
          </div>

          <div className={styles.filters_row}>
            <div className={styles.form_group}>
              <label className={styles.form_label} htmlFor="repository_id">
                Repository
              </label>
              <select
                id="repository_id"
                className={styles.form_select}
                value={filters.repository_id}
                onChange={(event) => handleInputChange("repository_id", event.target.value)}
              >
                <option value="">All repositories</option>
                {repositoryOptions}
              </select>
            </div>

            <div className={styles.form_group}>
              <label className={styles.form_label} htmlFor="language">
                Language
              </label>
              <select
                id="language"
                className={styles.form_select}
                value={filters.language}
                onChange={(event) => handleInputChange("language", event.target.value)}
              >
                <option value="">All</option>
                {languageOptions}
              </select>
            </div>

            <div className={styles.form_group}>
              <label className={styles.form_label} htmlFor="limit">
                Limit
              </label>
              <input
                id="limit"
                type="number"
                min={1}
                max={100}
                className={styles.form_input}
                value={filters.limit}
                onChange={(event) => handleInputChange("limit", event.target.value)}
              />
            </div>
          </div>

          <div className={styles.form_actions}>
            <button
              className={styles.secondary_button}
              type="reset"
              onClick={() => {
                setFilters(() => ({ ...initialFilters }));
                setResults([]);
                setSelectedSymbol(null);
              }}
            >
              Clear
            </button>
            <button className={styles.primary_button} type="submit" disabled={loading}>
              {loading ? "Searching..." : "Search"}
            </button>
          </div>
        </form>

        {error && (
          <div className={styles.error_banner}>
            <strong>Error:</strong> {error}
            <button className={styles.dismiss_button} onClick={() => setError(null)}>
              Dismiss
            </button>
          </div>
        )}

        <SearchResultsTable results={results} on_select_symbol={loadSymbolDetails} />
      </section>

      <aside className={styles.detail_panel}>
        <h2 className={styles.detail_title}>Symbol Details</h2>
        {symbolLoading && <p className={styles.detail_hint}>Loading symbol information...</p>}
        {!symbolLoading && !selectedSymbol && (
          <p className={styles.detail_hint}>Select a result to view parameters, documentation, and relationships.</p>
        )}
        {selectedSymbol && !symbolLoading && (
          <div className={styles.detail_content}>
            <div>
              <span className={styles.detail_label}>Name</span>
              <p className={styles.detail_value}>{selectedSymbol.name}</p>
            </div>
            {selectedSymbol.fully_qualified_name && (
              <div>
                <span className={styles.detail_label}>Fully Qualified</span>
                <code className={styles.detail_code}>{selectedSymbol.fully_qualified_name}</code>
              </div>
            )}
            <div>
              <span className={styles.detail_label}>Kind</span>
              <p className={styles.detail_value}>{selectedSymbol.kind}</p>
            </div>
            {selectedSymbol.signature && (
              <div>
                <span className={styles.detail_label}>Signature</span>
                <code className={styles.detail_code}>{selectedSymbol.signature}</code>
              </div>
            )}
            {selectedSymbol.documentation && (
              <div>
                <span className={styles.detail_label}>Documentation</span>
                <p className={styles.detail_value}>{selectedSymbol.documentation}</p>
              </div>
            )}
            <div>
              <span className={styles.detail_label}>Location</span>
              <p className={styles.detail_value}>
                File #{selectedSymbol.file_id} • Repository #{selectedSymbol.repository_id}
              </p>
            </div>
            <div>
              <span className={styles.detail_label}>Relationships</span>
              {selectedSymbol.relations.length === 0 ? (
                <p className={styles.detail_value}>No outbound relationships recorded.</p>
              ) : (
                <ul className={styles.relation_list}>
                  {selectedSymbol.relations.map((relation) => (
                    <li key={relation.id} className={styles.relation_item}>
                      <span className={styles.relation_type}>{relation.relation_type}</span>
                      <span className={styles.relation_target}>
                        #{relation.to_symbol_id} — {relation.to_symbol_name}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}


