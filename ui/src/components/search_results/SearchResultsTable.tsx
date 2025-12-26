import { SearchResult } from "../../services/api";
import styles from "./SearchResultsTable.module.css";

export type SearchResultsTableProps = {
  results: SearchResult[];
  on_select_symbol?: (result: SearchResult) => void;
};

function formatLocation(result: SearchResult): string {
  return `${result.file_path}:${result.start_line}-${result.end_line}`;
}

export default function SearchResultsTable({ results, on_select_symbol }: SearchResultsTableProps) {
  if (results.length === 0) {
    return (
      <div className={styles.empty_state}>
        <p>No results yet. Run a search to see matching symbols.</p>
      </div>
    );
  }

  return (
    <div className={styles.results_container}>
      <table className={styles.results_table}>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Repository</th>
            <th>Language</th>
            <th>Location</th>
            <th>Score</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {results.map((result) => (
            <tr key={`${result.symbol_id}-${result.file_id}`}>
              <td>
                <div className={styles.symbol_name}>{result.name}</div>
                {result.fully_qualified_name && (
                  <div className={styles.symbol_fqn}>{result.fully_qualified_name}</div>
                )}
              </td>
              <td>
                <div className={styles.repository_name}>{result.repository_name}</div>
              </td>
              <td>
                <span className={styles.language_badge}>{result.language}</span>
              </td>
              <td className={styles.location_cell}>{formatLocation(result)}</td>
              <td>{result.score.toFixed(2)}</td>
              <td>
                <button className={styles.detail_button} onClick={() => on_select_symbol?.(result)}>
                  View Details
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


