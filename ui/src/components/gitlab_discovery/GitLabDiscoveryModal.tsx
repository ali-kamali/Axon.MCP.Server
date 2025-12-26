import { FormEvent, useEffect, useState } from "react";

import {
  bulkAddRepositories,
  bulkRemoveRepositories,
  discoverGitLabProjects,
  type GitLabProjectDiscovery,
  type RepositoryCreatePayload,
} from "../../services/api";
import { SourceControlProviderEnum } from "../../types/enums";
import styles from "./GitLabDiscoveryModal.module.css";

interface GitLabDiscoveryModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export default function GitLabDiscoveryModal({ isOpen, onClose, onSuccess }: GitLabDiscoveryModalProps) {
  const [groupId, setGroupId] = useState("");
  const [loading, setLoading] = useState(false);
  const [discovering, setDiscovering] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [projects, setProjects] = useState<GitLabProjectDiscovery[]>([]);
  const [selectedProjects, setSelectedProjects] = useState<Set<number>>(new Set());
  const [discoveryComplete, setDiscoveryComplete] = useState(false);

  // Stats
  const [totalProjects, setTotalProjects] = useState(0);
  const [trackedCount, setTrackedCount] = useState(0);
  const [untrackedCount, setUntrackedCount] = useState(0);

  useEffect(() => {
    if (!isOpen) {
      // Reset state when modal closes
      setGroupId("");
      setProjects([]);
      setSelectedProjects(new Set());
      setDiscoveryComplete(false);
      setError(null);
    }
  }, [isOpen]);

  const handleDiscover = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!groupId.trim()) return;

    setDiscovering(true);
    setError(null);

    try {
      const response = await discoverGitLabProjects(groupId.trim());
      setProjects(response.projects);
      setTotalProjects(response.total_projects);
      setTrackedCount(response.tracked_count);
      setUntrackedCount(response.untracked_count);
      setDiscoveryComplete(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to discover GitLab projects");
    } finally {
      setDiscovering(false);
    }
  };

  const handleSelectAll = () => {
    const untracked = projects.filter((p) => !p.is_tracked);
    setSelectedProjects(new Set(untracked.map((p) => p.gitlab_project_id)));
  };

  const handleDeselectAll = () => {
    setSelectedProjects(new Set());
  };

  const handleToggleProject = (gitlabId: number) => {
    const newSelected = new Set(selectedProjects);
    if (newSelected.has(gitlabId)) {
      newSelected.delete(gitlabId);
    } else {
      newSelected.add(gitlabId);
    }
    setSelectedProjects(newSelected);
  };

  const handleAddSelected = async () => {
    if (selectedProjects.size === 0) return;

    setProcessing(true);
    setError(null);

    try {
      const repositoriesToAdd: RepositoryCreatePayload[] = projects
        .filter((p) => selectedProjects.has(p.gitlab_project_id) && !p.is_tracked)
        .map((p) => ({
          provider: SourceControlProviderEnum.gitlab,
          gitlab_project_id: p.gitlab_project_id,
          name: p.name,
          path_with_namespace: p.path_with_namespace,
          url: p.url,
          clone_url: p.url,
          default_branch: p.default_branch,
        }));

      const response = await bulkAddRepositories(repositoriesToAdd);

      if (response.failed_count > 0) {
        setError(`Added ${response.added_count}, failed ${response.failed_count}: ${response.errors.join(", ")}`);
      }

      // Refresh discovery to update tracking status
      const refreshed = await discoverGitLabProjects(groupId.trim());
      setProjects(refreshed.projects);
      setTrackedCount(refreshed.tracked_count);
      setUntrackedCount(refreshed.untracked_count);
      setSelectedProjects(new Set());

      if (response.added_count > 0) {
        onSuccess();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add repositories");
    } finally {
      setProcessing(false);
    }
  };

  const handleRemoveSelected = async () => {
    if (selectedProjects.size === 0) return;

    const confirmed = window.confirm(
      `Are you sure you want to remove ${selectedProjects.size} repositories? This will delete all associated data.`
    );
    if (!confirmed) return;

    setProcessing(true);
    setError(null);

    try {
      const repositoryIdsToRemove = projects
        .filter((p) => selectedProjects.has(p.gitlab_project_id) && p.is_tracked && p.tracked_repository_id)
        .map((p) => p.tracked_repository_id!);

      const response = await bulkRemoveRepositories(repositoryIdsToRemove);

      if (response.failed_count > 0) {
        setError(`Removed ${response.removed_count}, failed ${response.failed_count}: ${response.errors.join(", ")}`);
      }

      // Refresh discovery to update tracking status
      const refreshed = await discoverGitLabProjects(groupId.trim());
      setProjects(refreshed.projects);
      setTrackedCount(refreshed.tracked_count);
      setUntrackedCount(refreshed.untracked_count);
      setSelectedProjects(new Set());

      if (response.removed_count > 0) {
        onSuccess();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove repositories");
    } finally {
      setProcessing(false);
    }
  };

  if (!isOpen) return null;

  const selectedUntrackedCount = Array.from(selectedProjects).filter((id) => {
    const project = projects.find((p) => p.gitlab_project_id === id);
    return project && !project.is_tracked;
  }).length;

  const selectedTrackedCount = Array.from(selectedProjects).filter((id) => {
    const project = projects.find((p) => p.gitlab_project_id === id);
    return project && project.is_tracked;
  }).length;

  return (
    <div className={styles.modal_overlay} onClick={onClose}>
      <div className={styles.modal_content} onClick={(e) => e.stopPropagation()}>
        <div className={styles.modal_header}>
          <h2 className={styles.modal_title}>Discover GitLab Repositories</h2>
          <button className={styles.close_button} onClick={onClose} type="button">
            ✕
          </button>
        </div>

        {!discoveryComplete ? (
          <form onSubmit={handleDiscover} className={styles.discovery_form}>
            <div className={styles.form_row}>
              <label htmlFor="groupId" className={styles.form_label}>
                GitLab Group ID or Path
              </label>
              <input
                id="groupId"
                type="text"
                className={styles.form_input}
                value={groupId}
                onChange={(e) => setGroupId(e.target.value)}
                placeholder="e.g., mycompany or 12345"
                disabled={discovering}
                required
              />
              <p className={styles.field_hint}>Enter the GitLab group ID or path to discover all repositories</p>
            </div>

            {error && (
              <div className={styles.error_message}>
                <strong>Error:</strong> {error}
              </div>
            )}

            <div className={styles.form_actions}>
              <button type="button" className={styles.secondary_button} onClick={onClose} disabled={discovering}>
                Cancel
              </button>
              <button type="submit" className={styles.primary_button} disabled={discovering || !groupId.trim()}>
                {discovering ? "Discovering..." : "Discover Repositories"}
              </button>
            </div>
          </form>
        ) : (
          <div className={styles.results_container}>
            <div className={styles.stats_bar}>
              <div className={styles.stat_item}>
                <span className={styles.stat_label}>Total:</span>
                <span className={styles.stat_value}>{totalProjects}</span>
              </div>
              <div className={styles.stat_item}>
                <span className={styles.stat_label}>Tracked:</span>
                <span className={styles.stat_value_tracked}>{trackedCount}</span>
              </div>
              <div className={styles.stat_item}>
                <span className={styles.stat_label}>Untracked:</span>
                <span className={styles.stat_value_untracked}>{untrackedCount}</span>
              </div>
            </div>

            <div className={styles.selection_bar}>
              <div className={styles.selection_info}>
                {selectedProjects.size > 0 ? (
                  <span>
                    {selectedProjects.size} selected ({selectedUntrackedCount} untracked, {selectedTrackedCount}{" "}
                    tracked)
                  </span>
                ) : (
                  <span>No repositories selected</span>
                )}
              </div>
              <div className={styles.selection_actions}>
                <button
                  type="button"
                  className={styles.text_button}
                  onClick={handleSelectAll}
                  disabled={untrackedCount === 0}
                >
                  Select All Untracked
                </button>
                <button
                  type="button"
                  className={styles.text_button}
                  onClick={handleDeselectAll}
                  disabled={selectedProjects.size === 0}
                >
                  Deselect All
                </button>
              </div>
            </div>

            {error && (
              <div className={styles.error_message}>
                <strong>Error:</strong> {error}
              </div>
            )}

            <div className={styles.projects_list}>
              {projects.map((project) => (
                <div
                  key={project.gitlab_project_id}
                  className={`${styles.project_item} ${project.is_tracked ? styles.project_tracked : ""}`}
                >
                  <input
                    type="checkbox"
                    className={styles.project_checkbox}
                    checked={selectedProjects.has(project.gitlab_project_id)}
                    onChange={() => handleToggleProject(project.gitlab_project_id)}
                    disabled={processing}
                  />
                  <div className={styles.project_info}>
                    <div className={styles.project_header}>
                      <span className={styles.project_name}>{project.name}</span>
                      {project.is_tracked && <span className={styles.tracked_badge}>Tracked</span>}
                    </div>
                    <div className={styles.project_path}>{project.path_with_namespace}</div>
                    {project.description && <div className={styles.project_description}>{project.description}</div>}
                    <div className={styles.project_meta}>
                      <span>Branch: {project.default_branch}</span>
                      {project.visibility && <span>• {project.visibility}</span>}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className={styles.modal_footer}>
              <button type="button" className={styles.secondary_button} onClick={onClose} disabled={processing}>
                Close
              </button>
              <button
                type="button"
                className={styles.secondary_button}
                onClick={() => {
                  setDiscoveryComplete(false);
                  setProjects([]);
                  setSelectedProjects(new Set());
                }}
                disabled={processing}
              >
                Back to Search
              </button>
              {selectedTrackedCount > 0 && (
                <button
                  type="button"
                  className={styles.danger_button}
                  onClick={handleRemoveSelected}
                  disabled={processing || selectedTrackedCount === 0}
                >
                  {processing ? "Removing..." : `Remove ${selectedTrackedCount} Tracked`}
                </button>
              )}
              {selectedUntrackedCount > 0 && (
                <button
                  type="button"
                  className={styles.primary_button}
                  onClick={handleAddSelected}
                  disabled={processing || selectedUntrackedCount === 0}
                >
                  {processing ? "Adding..." : `Add ${selectedUntrackedCount} Repositories`}
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

