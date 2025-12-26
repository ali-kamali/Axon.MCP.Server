import { useEffect, useState } from "react";
import { getHealth, type HealthResponse } from "../../services/api";
import styles from "./SettingsPage.module.css";

export default function SettingsPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const apiBase = import.meta.env.VITE_API_BASE_URL || "(relative URLs - proxied by nginx)";
  const environment = import.meta.env.MODE ?? "development";
  const nodeEnv = import.meta.env.NODE_ENV ?? "development";
  
  useEffect(() => {
    async function loadHealth() {
      try {
        const data = await getHealth();
        setHealth(data);
      } catch (error) {
        console.error("Failed to load health data:", error);
      } finally {
        setLoading(false);
      }
    }
    void loadHealth();
  }, []);

  if (loading) {
    return (
      <div className={styles.settings_container}>
        <div className={styles.loading_message}>Loading settings...</div>
      </div>
    );
  }

  return (
    <div className={styles.settings_container}>
      <h1 className={styles.settings_title}>Settings & Configuration</h1>
      
      <section className={styles.settings_section}>
        <h2 className={styles.section_title}>API Configuration</h2>
        <div className={styles.settings_grid}>
          <div className={styles.setting_item}>
            <span className={styles.setting_label}>API Base URL</span>
            <code className={styles.setting_value}>{String(apiBase)}</code>
          </div>
          <div className={styles.setting_item}>
            <span className={styles.setting_label}>Build Environment</span>
            <code className={styles.setting_value}>{environment}</code>
          </div>
          <div className={styles.setting_item}>
            <span className={styles.setting_label}>Node Environment</span>
            <code className={styles.setting_value}>{nodeEnv}</code>
          </div>
        </div>
      </section>

      {!loading && health && (
        <section className={styles.settings_section}>
          <h2 className={styles.section_title}>Backend Information</h2>
          <div className={styles.settings_grid}>
            <div className={styles.setting_item}>
              <span className={styles.setting_label}>Service Name</span>
              <code className={styles.setting_value}>{health.service}</code>
            </div>
            <div className={styles.setting_item}>
              <span className={styles.setting_label}>Service Version</span>
              <code className={styles.setting_value}>{health.version}</code>
            </div>
            <div className={styles.setting_item}>
              <span className={styles.setting_label}>Environment</span>
              <code className={styles.setting_value}>{health.environment}</code>
            </div>
            <div className={styles.setting_item}>
              <span className={styles.setting_label}>Status</span>
              <span className={`${styles.status_badge} ${styles[`status_${health.status.toLowerCase()}`]}`}>
                {health.status}
              </span>
            </div>
          </div>
        </section>
      )}

      <section className={styles.settings_section}>
        <h2 className={styles.section_title}>Frontend Information</h2>
        <div className={styles.settings_grid}>
          <div className={styles.setting_item}>
            <span className={styles.setting_label}>React Version</span>
            <code className={styles.setting_value}>18.x</code>
          </div>
          <div className={styles.setting_item}>
            <span className={styles.setting_label}>Build Tool</span>
            <code className={styles.setting_value}>Vite</code>
          </div>
          <div className={styles.setting_item}>
            <span className={styles.setting_label}>UI Version</span>
            <code className={styles.setting_value}>1.1.0</code>
          </div>
        </div>
      </section>

      <section className={styles.settings_section}>
        <h2 className={styles.section_title}>Features</h2>
        <div className={styles.feature_list}>
          <div className={styles.feature_item}>
            <span className={styles.feature_icon}>✓</span>
            <span>Repository Management & Sync</span>
          </div>
          <div className={styles.feature_item}>
            <span className={styles.feature_icon}>✓</span>
            <span>Code Search & Symbol Navigation</span>
          </div>
          <div className={styles.feature_item}>
            <span className={styles.feature_icon}>✓</span>
            <span>File Browser with Tree View</span>
          </div>
          <div className={styles.feature_item}>
            <span className={styles.feature_icon}>✓</span>
            <span>Job Queue Monitoring</span>
          </div>
          <div className={styles.feature_item}>
            <span className={styles.feature_icon}>✓</span>
            <span>Worker Health Monitoring</span>
          </div>
          <div className={styles.feature_item}>
            <span className={styles.feature_icon}>✓</span>
            <span>GitLab Project Discovery</span>
          </div>
          <div className={styles.feature_item}>
            <span className={styles.feature_icon}>✓</span>
            <span>Bulk Operations (Sync, Delete)</span>
          </div>
          <div className={styles.feature_item}>
            <span className={styles.feature_icon}>✓</span>
            <span>Auto-Refresh Dashboard</span>
          </div>
          <div className={styles.feature_item}>
            <span className={styles.feature_icon}>✓</span>
            <span>Real-time Metrics & Health Status</span>
          </div>
        </div>
      </section>

      <section className={styles.settings_section}>
        <h2 className={styles.section_title}>About</h2>
        <p className={styles.about_text}>
          <strong>Axon MCP Server Dashboard</strong> provides comprehensive visibility and control
          over your code intelligence infrastructure. Monitor service health, manage GitLab repositories,
          search indexed code, track background jobs, and browse repository contents—all from a modern,
          responsive interface.
        </p>
        <p className={styles.about_text}>
          Built with React, TypeScript, and modern web technologies, this dashboard integrates with
          the Axon MCP Server backend to provide real-time insights into your codebase indexing and
          analysis pipeline.
        </p>
      </section>
    </div>
  );
}


