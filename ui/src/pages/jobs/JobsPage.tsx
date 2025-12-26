import { ChangeEvent, useCallback, useEffect, useMemo, useState } from "react";

import {
  cancelJob,
  getJob,
  listJobs,
  listWorkers,
  retryJob,
  type JobDetailResponse,
  type JobResponse,
  type PaginatedResult,
  type WorkerResponse,
} from "../../services/api";
import { JobStatusEnum, WorkerStatusEnum } from "../../types/enums";
import styles from "./JobsPage.module.css";

type StatusFilter = JobStatusEnum | "all";

const STATUS_OPTIONS: Array<{ label: string; value: StatusFilter }> = [
  { label: "All statuses", value: "all" },
  { label: "Pending", value: JobStatusEnum.pending },
  { label: "Running", value: JobStatusEnum.running },
  { label: "Completed", value: JobStatusEnum.completed },
  { label: "Failed", value: JobStatusEnum.failed },
  { label: "Cancelled", value: JobStatusEnum.cancelled },
  { label: "Retrying", value: JobStatusEnum.retrying },
];

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

function jobStatusLabel(status: JobStatusEnum): string {
  return status.toLowerCase().replace(/_/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function workerStatusLabel(status: WorkerStatusEnum): string {
  return status.toLowerCase().replace(/_/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function LogViewerModal({ repositoryId, onClose }: { repositoryId: number; onClose: () => void }) {
  const [logs, setLogs] = useState<Array<{ timestamp: string; message: string; level: string }>>([]);
  const [status, setStatus] = useState<"connecting" | "connected" | "disconnected">("connecting");

  useEffect(() => {
    const baseUrl = import.meta.env.VITE_API_BASE_URL || window.location.origin;
    const url = new URL(`/api/v1/repositories/${repositoryId}/logs`, baseUrl);
    url.protocol = url.protocol.replace("http", "ws");

    const ws = new WebSocket(url.toString());

    ws.onopen = () => {
      setStatus("connected");
      setLogs((prev) => [...prev, { timestamp: new Date().toISOString(), message: "Connected to log stream...", level: "INFO" }]);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setLogs((prev) => [...prev, data]);
      } catch (e) {
        setLogs((prev) => [...prev, { timestamp: new Date().toISOString(), message: event.data, level: "INFO" }]);
      }
    };

    ws.onclose = () => {
      setStatus("disconnected");
      setLogs((prev) => [...prev, { timestamp: new Date().toISOString(), message: "Connection closed.", level: "INFO" }]);
    };

    return () => {
      ws.close();
    };
  }, [repositoryId]);

  // Auto-scroll to bottom
  const logEndRef = useCallback((node: HTMLDivElement | null) => {
    if (node) {
      node.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs]);

  return (
    <div className={styles.modal_overlay} onClick={onClose}>
      <div className={styles.modal_content} onClick={(e) => e.stopPropagation()}>
        <div className={styles.modal_header}>
          <h3>Live Logs (Repository #{repositoryId})</h3>
          <div className={styles.connection_status}>
            <span className={`${styles.status_dot} ${styles[status]}`} />
            {status}
          </div>
          <button className={styles.close_button} onClick={onClose}>×</button>
        </div>
        <div className={styles.modal_body}>
          <div className={styles.log_viewer}>
            {logs.map((log, i) => (
              <div key={i} className={`${styles.log_line} ${styles[`log_${log.level?.toLowerCase()}`]}`}>
                <span className={styles.log_timestamp}>{new Date(log.timestamp).toLocaleTimeString()}</span>
                <span className={styles.log_message}>{log.message}</span>
              </div>
            ))}
            <div ref={logEndRef} />
          </div>
        </div>
      </div>
    </div>
  );
}

export default function JobsPage() {
  const [jobs, setJobs] = useState<JobResponse[]>([]);
  const [jobsMeta, setJobsMeta] = useState<Pick<PaginatedResult<JobResponse>, "total" | "limit" | "offset"> | null>(null);
  const [workers, setWorkers] = useState<WorkerResponse[]>([]);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [selectionLoading, setSelectionLoading] = useState(false);
  const [selectedJob, setSelectedJob] = useState<JobDetailResponse | null>(null);
  const [logModalRepoId, setLogModalRepoId] = useState<number | null>(null);

  const loadWorkers = useCallback(async () => {
    try {
      const data = await listWorkers();
      setWorkers(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to load worker status";
      setActionError(message);
    }
  }, []);

  const loadJobs = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const params: { limit?: number; offset?: number; status?: JobStatusEnum } = { limit: 25 };
      if (statusFilter !== "all") {
        params.status = statusFilter;
      }

      const response = await listJobs(params);
      setJobs(response.items);
      setJobsMeta({ total: response.total, limit: response.limit, offset: response.offset });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load jobs";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  const refreshAll = useCallback(async () => {
    await Promise.all([loadJobs(), loadWorkers()]);
  }, [loadJobs, loadWorkers]);

  useEffect(() => {
    void refreshAll();
  }, [refreshAll]);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

  const handleStatusChange = (event: ChangeEvent<HTMLSelectElement>) => {
    const next = event.target.value as StatusFilter;
    setStatusFilter(next);
  };

  const handleRetry = async (jobId: number) => {
    try {
      setActionError(null);
      setActionMessage(null);
      await retryJob(jobId);
      setActionMessage(`Retry requested for job #${jobId}.`);
      await loadJobs();
    } catch (err) {
      const message = err instanceof Error ? err.message : `Failed to retry job #${jobId}`;
      setActionError(message);
    }
  };

  const handleCancel = async (jobId: number) => {
    try {
      setActionError(null);
      setActionMessage(null);
      await cancelJob(jobId);
      setActionMessage(`Cancel request submitted for job #${jobId}.`);
      await loadJobs();
    } catch (err) {
      const message = err instanceof Error ? err.message : `Failed to cancel job #${jobId}`;
      setActionError(message);
    }
  };

  const handleSelectJob = async (jobId: number) => {
    setSelectionLoading(true);
    setActionError(null);
    try {
      const detail = await getJob(jobId);
      setSelectedJob(detail);
    } catch (err) {
      const message = err instanceof Error ? err.message : `Unable to load job #${jobId}`;
      setActionError(message);
    } finally {
      setSelectionLoading(false);
    }
  };

  const activeWorkers = useMemo(() => workers.filter((worker) => worker.status === WorkerStatusEnum.online).length, [workers]);

  const filteredJobsLabel = useMemo(() => {
    if (!jobsMeta) {
      return "";
    }
    const { total } = jobsMeta;
    if (statusFilter === "all") {
      return `${total} tracked jobs`;
    }
    return `${total} ${jobStatusLabel(statusFilter)} jobs`;
  }, [jobsMeta, statusFilter]);

  return (
    <div className={styles.jobs_container}>
      <header className={styles.jobs_header}>
        <div>
          <h1 className={styles.jobs_title}>Job Monitor</h1>
          <p className={styles.jobs_caption}>{filteredJobsLabel}</p>
        </div>
        <div className={styles.jobs_controls}>
          <select className={styles.filter_select} value={statusFilter} onChange={handleStatusChange}>
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <button className={styles.refresh_button} type="button" onClick={() => void refreshAll()}>
            Refresh
          </button>
        </div>
      </header>

      {error && <div className={styles.error_banner}>{error}</div>}
      {actionError && <div className={styles.inline_error}>Action failed: {actionError}</div>}
      {actionMessage && <div className={styles.success_banner}>{actionMessage}</div>}

      <div className={styles.jobs_layout}>
        <section className={styles.table_section}>
          <div className={styles.section_header}>
            <h2 className={styles.section_title}>Recent jobs</h2>
            <span className={styles.section_caption}>{jobs.length} of {jobsMeta?.total ?? 0}</span>
          </div>
          {loading ? (
            <p className={styles.section_hint}>Loading jobs…</p>
          ) : jobs.length === 0 ? (
            <p className={styles.section_hint}>No jobs found for the selected filter.</p>
          ) : (
            <table className={styles.jobs_table}>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Repository</th>
                  <th>Started</th>
                  <th>Duration</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.id}>
                    <td>
                      <button className={styles.link_button} type="button" onClick={() => void handleSelectJob(job.id)}>
                        #{job.id}
                      </button>
                    </td>
                    <td>{job.job_type}</td>
                    <td>
                      <span className={`${styles.status_pill} ${styles[`status_${job.status.toLowerCase()}`] ?? styles.status_default}`}>
                        {jobStatusLabel(job.status)}
                      </span>
                    </td>
                    <td>{job.repository_id ?? "—"}</td>
                    <td>{formatTimestamp(job.started_at)}</td>
                    <td>{formatDuration(job.duration_seconds)}</td>
                    <td>
                      <div className={styles.action_group}>
                        <button
                          className={styles.action_button}
                          type="button"
                          onClick={() => void handleRetry(job.id)}
                          disabled={job.status === JobStatusEnum.running || job.status === JobStatusEnum.pending}
                        >
                          Retry
                        </button>
                        <button
                          className={styles.action_button}
                          type="button"
                          onClick={() => void handleCancel(job.id)}
                          disabled={job.status !== JobStatusEnum.running && job.status !== JobStatusEnum.pending}
                        >
                          Cancel
                        </button>
                        {job.job_type === "sync_repository" && job.repository_id && (
                          <button
                            className={styles.action_button}
                            type="button"
                            onClick={() => setLogModalRepoId(job.repository_id!)}
                          >
                            Live Logs
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <aside className={styles.detail_panel}>
          <div className={styles.section_header}>
            <h2 className={styles.section_title}>Job details</h2>
            {selectionLoading && <span className={styles.section_caption}>Loading…</span>}
            {selectedJob && selectedJob.job_type === "sync_repository" && selectedJob.repository_id && (
              <button
                className={styles.refresh_button}
                onClick={() => setLogModalRepoId(selectedJob.repository_id!)}
                type="button"
              >
                Live Logs
              </button>
            )}
          </div>
          {!selectedJob && !selectionLoading && (
            <p className={styles.section_hint}>Select a job identifier to inspect payloads and errors.</p>
          )}
          {selectedJob && !selectionLoading && (
            <dl className={styles.detail_list}>
              <div className={styles.detail_row}>
                <dt>Status</dt>
                <dd>
                  <span className={`${styles.status_pill} ${styles[`status_${selectedJob.status.toLowerCase()}`] ?? styles.status_default}`}>
                    {jobStatusLabel(selectedJob.status)}
                  </span>
                </dd>
              </div>
              <div className={styles.detail_row}>
                <dt>Type</dt>
                <dd>{selectedJob.job_type}</dd>
              </div>
              <div className={styles.detail_row}>
                <dt>Repository</dt>
                <dd>{selectedJob.repository_id ?? "—"}</dd>
              </div>
              <div className={styles.detail_row}>
                <dt>Started</dt>
                <dd>{formatTimestamp(selectedJob.started_at)}</dd>
              </div>
              <div className={styles.detail_row}>
                <dt>Completed</dt>
                <dd>{formatTimestamp(selectedJob.completed_at)}</dd>
              </div>
              <div className={styles.detail_row}>
                <dt>Duration</dt>
                <dd>{formatDuration(selectedJob.duration_seconds)}</dd>
              </div>
              <div className={styles.detail_row}>
                <dt>Retries</dt>
                <dd>
                  {selectedJob.retry_count}/{selectedJob.max_retries}
                </dd>
              </div>
              {selectedJob.error_message && (
                <div className={styles.detail_row}>
                  <dt>Error message</dt>
                  <dd className={styles.error_text}>{selectedJob.error_message}</dd>
                </div>
              )}
              {selectedJob.error_traceback && (
                <div className={styles.detail_row}>
                  <dt>Traceback</dt>
                  <dd className={styles.traceback_block}>{selectedJob.error_traceback}</dd>
                </div>
              )}
              {selectedJob.job_metadata && (
                <div className={styles.detail_row}>
                  <dt>Metadata</dt>
                  <dd className={styles.metadata_block}>{JSON.stringify(selectedJob.job_metadata, null, 2)}</dd>
                </div>
              )}
            </dl>
          )}
        </aside>
      </div>

      <section className={styles.workers_section}>
        <div className={styles.section_header}>
          <h2 className={styles.section_title}>Celery workers</h2>
          <span className={styles.section_caption}>{activeWorkers} online</span>
        </div>
        {workers.length === 0 ? (
          <p className={styles.section_hint}>No worker heartbeat data available.</p>
        ) : (
          <table className={styles.workers_table}>
            <thead>
              <tr>
                <th>Hostname</th>
                <th>Status</th>
                <th>Last heartbeat</th>
                <th>Current job</th>
                <th>Queues</th>
              </tr>
            </thead>
            <tbody>
              {workers.map((worker) => (
                <tr key={worker.id}>
                  <td>{worker.hostname}</td>
                  <td>
                    <span className={`${styles.worker_badge} ${styles[`worker_${worker.status.toLowerCase()}`] ?? styles.worker_unknown}`}>
                      {workerStatusLabel(worker.status)}
                    </span>
                  </td>
                  <td>{worker.last_heartbeat_at ? formatTimestamp(worker.last_heartbeat_at) : "—"}</td>
                  <td>{worker.current_job_id ?? "—"}</td>
                  <td>{worker.queues.length === 0 ? "—" : worker.queues.join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {logModalRepoId && (
        <LogViewerModal
          repositoryId={logModalRepoId}
          onClose={() => setLogModalRepoId(null)}
        />
      )}
    </div>
  );
}


