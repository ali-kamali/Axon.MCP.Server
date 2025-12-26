import { Link } from "react-router-dom";

import { RepositoryResponse } from "../../services/api";
import { RepositoryStatusEnum, SourceControlProviderEnum } from "../../types/enums";
import styles from "./RepoTable.module.css";

export type RepoTableProps = {
  rows: RepositoryResponse[];
  on_sync_click?: (row: RepositoryResponse) => void;
  on_delete_click?: (row: RepositoryResponse) => void;
  on_edit_click?: (row: RepositoryResponse) => void;
  selectedIds?: number[];
  onToggleSelection?: (id: number) => void;
  onToggleAll?: () => void;
};

function formatTimestamp(value: string | null): string {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  return date.toLocaleString();
}

function formatSize(bytes: number): string {
  if (bytes <= 0) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** exponent;
  return `${value.toFixed(value < 10 ? 2 : 1)} ${units[exponent]}`;
}

function statusLabel(status: RepositoryStatusEnum): string {
  return status.toLowerCase().replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function RepoTable({
  rows,
  on_sync_click,
  on_delete_click,
  on_edit_click,
  selectedIds = [],
  onToggleSelection,
  onToggleAll,
}: RepoTableProps) {
  const hasSelection = selectedIds.length > 0;
  const allSelected = rows.length > 0 && selectedIds.length === rows.length;

  return (
    <div className={styles.repo_table_wrapper}>
      <table className={styles.repo_table}>
        <thead>
          <tr className={styles.repo_table_header}>
            {onToggleSelection && (
              <th className={styles.checkbox_column}>
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={onToggleAll}
                  aria-label="Select all repositories"
                />
              </th>
            )}
            <th>ID</th>
            <th>Provider</th>
            <th>Name</th>
            <th>Language</th>
            <th>Path</th>
            <th>Status</th>
            <th>Last Sync</th>
            <th>Last Commit</th>
            <th>Files</th>
            <th>Symbols</th>
            <th>Size</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((repo) => (
            <tr key={repo.id} className={styles.repo_table_row}>
              {onToggleSelection && (
                <td className={styles.checkbox_column}>
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(repo.id)}
                    onChange={() => onToggleSelection(repo.id)}
                    aria-label={`Select ${repo.name}`}
                  />
                </td>
              )}
              <td>{repo.id}</td>
              <td>
                <span className={`${styles.provider_badge} ${styles[`provider_${repo.provider.toLowerCase()}`]}`}>
                  {repo.provider === SourceControlProviderEnum.gitlab ? 'GitLab' : 'Azure DevOps'}
                </span>
              </td>
              <td>
                <div className={styles.repo_name}>{repo.name}</div>
                <div className={styles.repo_branch}>Branch: {repo.default_branch}</div>
              </td>
              <td>
                {repo.primary_language || '—'}
              </td>
              <td className={styles.repo_path}>{repo.path_with_namespace}</td>
              <td>
                <span className={`${styles.status_pill} ${styles[`status_${repo.status.toLowerCase()}`]}`}>
                  {statusLabel(repo.status)}
                </span>
              </td>
              <td>{formatTimestamp(repo.last_synced_at)}</td>
              <td>
                {repo.last_commit ? (
                  <div title={repo.last_commit.message}>
                    <div className={styles.commit_message}>{repo.last_commit.message.split('\n')[0].slice(0, 30)}{repo.last_commit.message.length > 30 ? '...' : ''}</div>
                    <div className={styles.commit_meta}>{formatTimestamp(repo.last_commit.committed_date)}</div>
                  </div>
                ) : (
                  '—'
                )}
              </td>
              <td>{repo.total_files}</td>
              <td>{repo.total_symbols}</td>
              <td>{formatSize(repo.size_bytes)}</td>
              <td>
                <div className={styles.action_group}>
                  <Link to={`/repositories/${repo.id}`} className={styles.view_link}>
                    View
                  </Link>
                  {on_edit_click && (
                    <button
                      className={styles.edit_button}
                      onClick={() => on_edit_click(repo)}
                      type="button"
                      title="Edit repository"
                    >
                      Edit
                    </button>
                  )}
                  <button
                    className={styles.sync_button}
                    onClick={() => on_sync_click?.(repo)}
                    type="button"
                    disabled={!on_sync_click}
                    title="Sync repository"
                  >
                    Sync
                  </button>
                  {on_delete_click && (
                    <button
                      className={styles.delete_button}
                      onClick={() => on_delete_click(repo)}
                      type="button"
                      title="Delete repository"
                    >
                      Delete
                    </button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


