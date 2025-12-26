import { FormEvent, useEffect, useState } from "react";

import {
  bulkAddRepositories,
  bulkRemoveRepositories,
  discoverAzureDevOpsRepositories,
  type AzureDevOpsRepositoryDiscovery,
  type RepositoryCreatePayload,
} from "../../services/api";
import { SourceControlProviderEnum } from "../../types/enums";
import styles from "./AzureDevOpsDiscoveryModal.module.css";

interface AzureDevOpsDiscoveryModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export default function AzureDevOpsDiscoveryModal({ isOpen, onClose, onSuccess }: AzureDevOpsDiscoveryModalProps) {
  const [projectName, setProjectName] = useState("");
  const [loading, setLoading] = useState(false);
  const [discovering, setDiscovering] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [repositories, setRepositories] = useState<AzureDevOpsRepositoryDiscovery[]>([]);
  const [selectedRepositories, setSelectedRepositories] = useState<Set<string>>(new Set());
  const [discoveryComplete, setDiscoveryComplete] = useState(false);

  // Stats
  const [totalRepositories, setTotalRepositories] = useState(0);
  const [trackedCount, setTrackedCount] = useState(0);
  const [untrackedCount, setUntrackedCount] = useState(0);

  useEffect(() => {
    if (!isOpen) {
      // Reset state when modal closes
      setProjectName("");
      setRepositories([]);
      setSelectedRepositories(new Set());
      setDiscoveryComplete(false);
      setError(null);
    }
  }, [isOpen]);

  const handleDiscover = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!projectName.trim()) return;

    setDiscovering(true);
    setError(null);

    try {
      const response = await discoverAzureDevOpsRepositories(projectName.trim());
      setRepositories(response.repositories);
      setTotalRepositories(response.total_repositories);
      setTrackedCount(response.tracked_count);
      setUntrackedCount(response.untracked_count);
      setDiscoveryComplete(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to discover Azure DevOps repositories");
    } finally {
      setDiscovering(false);
    }
  };

  const handleSelectAll = () => {
    const untracked = repositories.filter((r) => !r.is_tracked);
    setSelectedRepositories(new Set(untracked.map((r) => r.azuredevops_repo_id)));
  };

  const handleDeselectAll = () => {
    setSelectedRepositories(new Set());
  };

  const handleToggleRepository = (repoId: string) => {
    const newSelected = new Set(selectedRepositories);
    if (newSelected.has(repoId)) {
      newSelected.delete(repoId);
    } else {
      newSelected.add(repoId);
    }
    setSelectedRepositories(newSelected);
  };

  const handleAddSelected = async () => {
    if (selectedRepositories.size === 0) return;

    setProcessing(true);
    setError(null);

    try {
      const repositoriesToAdd: RepositoryCreatePayload[] = repositories
        .filter((r) => selectedRepositories.has(r.azuredevops_repo_id) && !r.is_tracked)
        .map((r) => ({
          provider: SourceControlProviderEnum.azuredevops,
          azuredevops_project_name: r.azuredevops_project_name,
          azuredevops_repo_id: r.azuredevops_repo_id,
          name: r.name,
          path_with_namespace: r.path_with_namespace,
          url: r.url,
          clone_url: r.clone_url,
          default_branch: r.default_branch,
        }));

      const response = await bulkAddRepositories(repositoriesToAdd);

      if (response.failed_count > 0) {
        setError(`Added ${response.added_count}, failed ${response.failed_count}: ${response.errors.join(", ")}`);
      }

      // Refresh discovery to update tracking status
      const refreshed = await discoverAzureDevOpsRepositories(projectName.trim());
      setRepositories(refreshed.repositories);
      setTrackedCount(refreshed.tracked_count);
      setUntrackedCount(refreshed.untracked_count);
      setSelectedRepositories(new Set());

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
    if (selectedRepositories.size === 0) return;

    const confirmed = window.confirm(
      `Are you sure you want to remove ${selectedRepositories.size} repositories? This will delete all associated data.`
    );
    if (!confirmed) return;

    setProcessing(true);
    setError(null);

    try {
      const repositoryIdsToRemove = repositories
        .filter((r) => selectedRepositories.has(r.azuredevops_repo_id) && r.is_tracked && r.tracked_repository_id)
        .map((r) => r.tracked_repository_id!);

      const response = await bulkRemoveRepositories(repositoryIdsToRemove);

      if (response.failed_count > 0) {
        setError(`Removed ${response.removed_count}, failed ${response.failed_count}: ${response.errors.join(", ")}`);
      }

      // Refresh discovery to update tracking status
      const refreshed = await discoverAzureDevOpsRepositories(projectName.trim());
      setRepositories(refreshed.repositories);
      setTrackedCount(refreshed.tracked_count);
      setUntrackedCount(refreshed.untracked_count);
      setSelectedRepositories(new Set());

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

  const selectedUntrackedCount = Array.from(selectedRepositories).filter((id) => {
    const repository = repositories.find((r) => r.azuredevops_repo_id === id);
    return repository && !repository.is_tracked;
  }).length;

  const selectedTrackedCount = Array.from(selectedRepositories).filter((id) => {
    const repository = repositories.find((r) => r.azuredevops_repo_id === id);
    return repository && repository.is_tracked;
  }).length;

  return (
    <div className={styles.modal_overlay} onClick={onClose}>
      <div className={styles.modal_content} onClick={(e) => e.stopPropagation()}>
        <div className={styles.modal_header}>
          <h2 className={styles.modal_title}>Discover Azure DevOps Repositories</h2>
          <button className={styles.close_button} onClick={onClose} type="button">
            ✕
          </button>
        </div>

        {!discoveryComplete ? (
          <form onSubmit={handleDiscover} className={styles.discovery_form}>
            <div className={styles.form_row}>
              <label htmlFor="projectName" className={styles.form_label}>
                Azure DevOps Project Name
              </label>
              <input
                id="projectName"
                type="text"
                className={styles.form_input}
                value={projectName}
                onChange={(e) => setProjectName(e.target.value)}
                placeholder="e.g., MyProject"
                disabled={discovering}
                required
              />
              <p className={styles.field_hint}>Enter the Azure DevOps project name to discover all repositories</p>
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
              <button type="submit" className={styles.primary_button} disabled={discovering || !projectName.trim()}>
                {discovering ? "Discovering..." : "Discover Repositories"}
              </button>
            </div>
          </form>
        ) : (
          <div className={styles.results_container}>
            <div className={styles.stats_bar}>
              <div className={styles.stat_item}>
                <span className={styles.stat_label}>Total:</span>
                <span className={styles.stat_value}>{totalRepositories}</span>
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
                {selectedRepositories.size > 0 ? (
                  <span>
                    {selectedRepositories.size} selected ({selectedUntrackedCount} untracked, {selectedTrackedCount}{" "}
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
                  disabled={selectedRepositories.size === 0}
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

            <div className={styles.repositories_list}>
              {repositories.map((repository) => (
                <div
                  key={repository.azuredevops_repo_id}
                  className={`${styles.repository_item} ${repository.is_tracked ? styles.repository_tracked : ""}`}
                >
                  <input
                    type="checkbox"
                    className={styles.repository_checkbox}
                    checked={selectedRepositories.has(repository.azuredevops_repo_id)}
                    onChange={() => handleToggleRepository(repository.azuredevops_repo_id)}
                    disabled={processing}
                  />
                  <div className={styles.repository_info}>
                    <div className={styles.repository_header}>
                      <span className={styles.repository_name}>{repository.name}</span>
                      {repository.is_tracked && <span className={styles.tracked_badge}>Tracked</span>}
                    </div>
                    <div className={styles.repository_path}>{repository.path_with_namespace}</div>
                    {repository.description && <div className={styles.repository_description}>{repository.description}</div>}
                    <div className={styles.repository_meta}>
                      <span>Branch: {repository.default_branch}</span>
                      <span>• Project: {repository.azuredevops_project_name}</span>
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
                  setRepositories([]);
                  setSelectedRepositories(new Set());
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
