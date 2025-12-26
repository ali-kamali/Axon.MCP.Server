import { useCallback, useEffect, useState } from "react";
import HealthCard from "../../components/health_card/HealthCard";
import MetricsPanel from "../../components/metrics_panel/MetricsPanel";
import { OverviewStats } from "../../components/Statistics/OverviewStats";
import { getHealth, getMetricsRaw, type HealthResponse } from "../../services/api";
import { useAutoRefresh } from "../../hooks/useAutoRefresh";
import styles from "./DashboardPage.module.css";

export default function DashboardPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [metrics, setMetrics] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [autoRefreshInterval, setAutoRefreshInterval] = useState(30);

  const loadDashboard = useCallback(async (options: { silent?: boolean } = {}) => {
    const { silent = false } = options;
    if (silent) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    try {
      setError(null);

      const [healthData, metricsData] = await Promise.all([
        getHealth(),
        getMetricsRaw(),
      ]);

      setHealth(healthData);
      setMetrics(metricsData);
      setLastUpdated(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch data");
    } finally {
      if (silent) {
        setRefreshing(false);
      } else {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  const refreshDashboard = useCallback(() => {
    void loadDashboard({ silent: true });
  }, [loadDashboard]);

  const autoRefresh = useAutoRefresh({
    enabled: false,
    interval: autoRefreshInterval * 1000,
    onRefresh: refreshDashboard,
  });

  const formattedTimestamp = lastUpdated ? lastUpdated.toLocaleTimeString() : null;

  if (loading) {
    return (
      <div className={styles.dashboard_container}>
        <div className={styles.loading_message}>Loading dashboard data...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.dashboard_container}>
        <div className={styles.error_message}>
          <strong>Error:</strong> {error}
        </div>
      </div>
    );
  }

  return (
    <div className={styles.dashboard_container}>
      <div className={styles.dashboard_header}>
        <div>
          <h1 className={styles.dashboard_title}>Dashboard</h1>
          {formattedTimestamp && (
            <p className={styles.dashboard_caption}>
              Last updated {formattedTimestamp}
              {autoRefresh.isEnabled && ` • Auto-refreshing every ${autoRefreshInterval}s`}
            </p>
          )}
        </div>
        <div className={styles.dashboard_actions}>
          <select
            className={styles.interval_select}
            value={autoRefreshInterval}
            onChange={(e) => {
              const newInterval = Number(e.target.value);
              setAutoRefreshInterval(newInterval);
              autoRefresh.updateInterval(newInterval * 1000);
            }}
          >
            <option value={10}>10s</option>
            <option value={30}>30s</option>
            <option value={60}>1min</option>
            <option value={120}>2min</option>
            <option value={300}>5min</option>
          </select>
          <button
            type="button"
            className={autoRefresh.isEnabled ? styles.auto_refresh_active : styles.auto_refresh_button}
            onClick={autoRefresh.toggle}
          >
            {autoRefresh.isEnabled ? "Stop Auto-Refresh" : "Start Auto-Refresh"}
          </button>
          <button
            type="button"
            className={styles.refresh_button}
            onClick={refreshDashboard}
            disabled={refreshing}
          >
            {refreshing ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      </div>

      {/* Architecture Overview Section */}
      <div className={styles.architecture_section}>
        <h2 className={styles.section_title}>System Architecture</h2>
        <p className={styles.section_description}>
          Axon MCP Server acts as the central intelligence hub, connecting raw repositories from GitLab and Azure DevOps
          with AI agent consumers through the Model Context Protocol (MCP).
        </p>
        <div className={styles.architecture_image_container}>
          <img
            src="/architecture-diagram.jpg"
            alt="Axon MCP Server Architecture Diagram"
            className={styles.architecture_image}
          />
        </div>
      </div>

      <div className={styles.stats_section}>
        <OverviewStats />
      </div>

      <div className={styles.dashboard_grid}>
        {health && (
          <HealthCard
            status={health.status}
            service={health.service}
            version={health.version}
            environment={health.environment}
          />
        )}
        <MetricsPanel metrics_text={metrics} />
      </div>
    </div>
  );
}


