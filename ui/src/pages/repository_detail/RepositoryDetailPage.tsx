import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  getRepository,
  getRepositoryStats,
  getRepositorySyncHistory,
  syncRepository,
  type PaginatedResult,
  type RepositoryResponse,
  type RepositoryStatsResponse,
  type RepositorySyncAttempt,
} from "../../services/api";
import { JobStatusEnum, RepositoryStatusEnum, SourceControlProviderEnum } from "../../types/enums";
import { RepositoryStats } from "../../components/Statistics/RepositoryStats";
import SampleDataTabs from "../../components/Repository/SampleDataTabs";
import { AnalysisResults } from "../../components/Repository/AnalysisResults";
import styles from "./RepositoryDetailPage.module.css";

type RouteParams = {
  repositoryId: string;
};

type HistoryState = PaginatedResult<RepositorySyncAttempt> | null;

function formatTimestamp(value: string | null): string {
  if (!value) {
    return "—";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

function formatDuration(seconds: number | null): string {
  if (seconds === null || Number.isNaN(seconds)) {
    return "—";
  }

  if (seconds < 60) {
    return `${seconds.toFixed(1)}s`;
  }

  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return remainingSeconds === 0 ? `${minutes}m` : `${minutes}m ${remainingSeconds.toFixed(0)}s`;
}

function formatBytes(value: number): string {
  if (value <= 0) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  const exponent = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  const converted = value / 1024 ** exponent;
  return `${converted.toFixed(converted < 10 ? 1 : 0)} ${units[exponent]}`;
}

function repositoryStatusLabel(status: RepositoryStatusEnum): string {
  return status.toLowerCase().replace(/_/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function jobStatusLabel(status: JobStatusEnum): string {
  return status.toLowerCase().replace(/_/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

export default function RepositoryDetailPage() {
  const { repositoryId } = useParams<RouteParams>();
  const repositoryIdNumber = Number(repositoryId);

  const [repository, setRepository] = useState<RepositoryResponse | null>(null);
  const [stats, setStats] = useState<RepositoryStatsResponse | null>(null);
  const [history, setHistory] = useState<HistoryState>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notification, setNotification] = useState<string | null>(null);

  const loadData = useCallback(
    async (options: { silent?: boolean } = {}) => {
      if (Number.isNaN(repositoryIdNumber)) {
        setPageError("Repository identifier is invalid.");
        setLoading(false);
        return;
      }

      const { silent = false } = options;
      if (silent) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }

      try {
        setPageError(null);
        setActionError(null);

        const [repositoryData, statsData, historyData] = await Promise.all([
          getRepository(repositoryIdNumber),
          getRepositoryStats(repositoryIdNumber),
          getRepositorySyncHistory(repositoryIdNumber, { limit: 15 }),
        ]);

        setRepository(repositoryData);
        setStats(statsData);
        setHistory(historyData);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to load repository details";
        setPageError(message);
      } finally {
        if (silent) {
          setRefreshing(false);
        } else {
          setLoading(false);
        }
      }
    },
    [repositoryIdNumber]
  );

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const triggerSync = async () => {
    if (!repository) {
      return;
    }

    try {
      setSyncing(true);
      setActionError(null);
      await syncRepository(repository.id);
      setNotification(`Manual sync queued for ${repository.name}.`);
      void loadData({ silent: true });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to trigger sync";
      setActionError(message);
    } finally {
      setSyncing(false);
    }
  };

  const closeNotification = () => {
    setNotification(null);
  };

  const languageBreakdown = useMemo(() => {
    if (!stats) {
      return [] as Array<{ language: string; value: number; percentage: number }>;
    }
    const entries = Object.entries(stats.languages ?? {});
    const total = entries.reduce((acc, [, value]) => acc + value, 0);
    if (total === 0) {
      return [];
    }
    return entries
      .map(([language, value]) => ({
        language,
        value,
        percentage: (value / total) * 100,
      }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 8);
  }, [stats]);

  const symbolBreakdown = useMemo(() => {
    if (!stats) {
      return [] as Array<{ kind: string; value: number; percentage: number }>;
    }
    const entries = Object.entries(stats.symbol_kinds ?? {});
    const total = entries.reduce((acc, [, value]) => acc + value, 0);
    if (total === 0) {
      return [];
    }
    return entries
      .map(([kind, value]) => ({
        kind,
        value,
        percentage: (value / total) * 100,
      }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 8);
  }, [stats]);

  if (Number.isNaN(repositoryIdNumber)) {
    return (
      <div className={styles.detail_container}>
        <div className={styles.error_banner}>Repository identifier must be a number.</div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className={styles.detail_container}>
        <div className={styles.loading_panel}>Loading repository details...</div>
      </div>
    );
  }

  if (pageError || !repository) {
    return (
      <div className={styles.detail_container}>
        <div className={styles.error_banner}>
          <strong>Error:</strong> {pageError ?? "Repository not found"}
          <div className={styles.error_actions}>
            <Link className={styles.secondary_button} to="/repositories">
              Back to repositories
            </Link>
            <button className={styles.primary_button} type="button" onClick={() => loadData({ silent: false })}>
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.detail_container}>
      <header className={styles.detail_header}>
        <div className={styles.header_text_group}>
          <div className={styles.breadcrumbs}>
            <Link to="/repositories" className={styles.breadcrumb_link}>
              Repositories
            </Link>
            <span className={styles.breadcrumb_separator}>/</span>
            <span>{repository.name}</span>
          </div>
          <div className={styles.title_row}>
            <h1 className={styles.detail_title}>{repository.name}</h1>
            <span className={`${styles.status_pill} ${styles[`status_${repository.status.toLowerCase()}`] ?? styles.status_default}`}>
              {repositoryStatusLabel(repository.status)}
            </span>
          </div>
          <p className={styles.detail_subtitle}>{repository.path_with_namespace}</p>
          <div className={styles.detail_meta}>
            <span>ID #{repository.id}</span>
            <span>GitLab #{repository.gitlab_project_id}</span>
            <span>Default branch {repository.default_branch}</span>
          </div>
        </div>
        <div className={styles.header_actions}>
          <Link className={styles.secondary_button} to={`/repositories/${repository.id}/files`}>
            Browse files
          </Link>
          <Link className={styles.secondary_button} to={`/search?repository_id=${repository.id}`}>
            Search symbols
          </Link>
          <button
            className={styles.primary_button}
            type="button"
            onClick={triggerSync}
            disabled={syncing}
          >
            {syncing ? "Triggering..." : "Trigger sync"}
          </button>
          <button
            className={styles.refresh_button}
            type="button"
            onClick={() => loadData({ silent: true })}
            disabled={refreshing}
          >
            {refreshing ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      </header>

      {notification && (
        <div className={styles.success_banner} role="status">
          <span>{notification}</span>
          <button className={styles.dismiss_button} type="button" onClick={closeNotification}>
            Dismiss
          </button>
        </div>
      )}

      {actionError && (
        <div className={styles.inline_error} role="alert">
          <strong>Action failed:</strong> {actionError}
        </div>
      )}

      <section className={styles.summary_section}>
        <h2 className={styles.section_title}>Repository summary</h2>
        <div className={styles.summary_grid}>
          <article className={styles.summary_card}>
            <span className={styles.summary_label}>Size</span>
            <span className={styles.summary_value}>{formatBytes(repository.size_bytes)}</span>
          </article>
          <article className={styles.summary_card}>
            <span className={styles.summary_label}>Files indexed</span>
            <span className={styles.summary_value}>{repository.total_files.toLocaleString()}</span>
          </article>
          <article className={styles.summary_card}>
            <span className={styles.summary_label}>Symbols indexed</span>
            <span className={styles.summary_value}>{repository.total_symbols.toLocaleString()}</span>
          </article>
          <article className={styles.summary_card}>
            <span className={styles.summary_label}>Last sync</span>
            <span className={styles.summary_value}>{formatTimestamp(repository.last_synced_at)}</span>
          </article>
          <article className={styles.summary_card}>
            <span className={styles.summary_label}>Last commit</span>
            <span className={styles.summary_value}>{repository.last_commit_sha ?? "—"}</span>
          </article>
          <article className={styles.summary_card}>
            <span className={styles.summary_label}>URL</span>
            <a className={styles.summary_link} href={repository.url} target="_blank" rel="noreferrer">
              {repository.provider === SourceControlProviderEnum.azuredevops ? "Open in Azure DevOps" : "Open in GitLab"}
            </a>
          </article>
        </div>
      </section>

      <section className={styles.analysis_section}>
        <AnalysisResults repositoryId={repository.id} />
      </section>

      <section className={styles.stats_section}>
        <div className={styles.stats_header}>
          <h2 className={styles.section_title}>Detailed Statistics</h2>
        </div>
        <RepositoryStats repositoryId={repository.id} />
      </section>

      <section className={styles.history_section}>
        <div className={styles.stats_header}>
          <h2 className={styles.section_title}>Recent sync attempts</h2>
          <span className={styles.section_caption}>
            {history?.total ? `${history.total} total attempts` : "No sync history recorded"}
          </span>
        </div>
        {history && history.items.length > 0 ? (
          <table className={styles.history_table}>
            <thead>
              <tr>
                <th>ID</th>
                <th>Status</th>
                <th>Triggered</th>
                <th>Completed</th>
                <th>Duration</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              {history.items.map((attempt) => (
                <tr key={attempt.id}>
                  <td>{attempt.id}</td>
                  <td>
                    <span className={`${styles.status_pill} ${styles[`job_${attempt.status.toLowerCase()}`] ?? styles.status_default}`}>
                      {jobStatusLabel(attempt.status)}
                    </span>
                  </td>
                  <td>{formatTimestamp(attempt.triggered_at)}</td>
                  <td>{formatTimestamp(attempt.completed_at)}</td>
                  <td>{formatDuration(attempt.duration_seconds)}</td>
                  <td className={styles.history_error}>{attempt.error_message ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className={styles.section_hint}>No sync attempts have been recorded for this repository.</p>
        )}
      </section>

      <section className={styles.samples_section}>
        <SampleDataTabs repositoryId={repository.id} />
      </section>
    </div>
  );
}


