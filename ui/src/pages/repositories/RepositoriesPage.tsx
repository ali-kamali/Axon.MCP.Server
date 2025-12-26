import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import ConfirmationModal from "../../components/confirmation_modal/ConfirmationModal";
import GitLabDiscoveryModal from "../../components/gitlab_discovery/GitLabDiscoveryModal";
import AzureDevOpsDiscoveryModal from "../../components/azuredevops_discovery/AzureDevOpsDiscoveryModal";
import Pagination from "../../components/pagination/Pagination";
import RepoTable from "../../components/repo_table/RepoTable";
import Toast, { ToastTypeEnum } from "../../components/toast/Toast";
import {
  bulkDeleteRepositories,
  bulkSyncRepositories,
  createRepository,
  deleteRepository,
  listRepositories,
  syncRepository,
  updateRepository,
  type RepositoryCreatePayload,
  type RepositoryResponse,
  type RepositoryUpdatePayload,
} from "../../services/api";
import { enrichmentService } from "../../services/enrichmentService";
import { RepositoryStatusEnum, SourceControlProviderEnum } from "../../types/enums";
import styles from "./RepositoriesPage.module.css";

type FormState = {
  provider: SourceControlProviderEnum;
  gitlab_project_id: string;
  azuredevops_project_name: string;
  azuredevops_repo_id: string;
  name: string;
  path_with_namespace: string;
  url: string;
  clone_url: string;
  default_branch: string;
};

const initialFormState: FormState = {
  provider: SourceControlProviderEnum.gitlab,
  gitlab_project_id: "",
  azuredevops_project_name: "",
  azuredevops_repo_id: "",
  name: "",
  path_with_namespace: "",
  url: "",
  clone_url: "",
  default_branch: "main",
};

const ITEMS_PER_PAGE = 20;

export default function RepositoriesPage() {
  const [repositories, setRepositories] = useState<RepositoryResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [syncingId, setSyncingId] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [formState, setFormState] = useState<FormState>(initialFormState);
  const [showForm, setShowForm] = useState(false);
  const [showGitLabDiscoveryModal, setShowGitLabDiscoveryModal] = useState(false);
  const [showAzureDevOpsDiscoveryModal, setShowAzureDevOpsDiscoveryModal] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalItems, setTotalItems] = useState(0);

  // New state for enhanced features
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [editingRepo, setEditingRepo] = useState<RepositoryResponse | null>(null);
  const [deletingRepo, setDeletingRepo] = useState<RepositoryResponse | null>(null);
  const [showBulkDeleteConfirm, setShowBulkDeleteConfirm] = useState(false);
  const [bulkOperationInProgress, setBulkOperationInProgress] = useState(false);
  const [deletingInProgress, setDeletingInProgress] = useState(false);
  const [toastMessage, setToastMessage] = useState<{ message: string; type: ToastTypeEnum } | null>(null);

  useEffect(() => {
    void fetchRepositories();
  }, [currentPage]);

  const activeRepositoryCount = useMemo(
    () => repositories.filter((repo) => repo.status !== RepositoryStatusEnum.failed).length,
    [repositories]
  );

  const fetchRepositories = async () => {
    try {
      setLoading(true);
      setError(null);
      const skip = (currentPage - 1) * ITEMS_PER_PAGE;
      const data = await listRepositories({ skip, limit: ITEMS_PER_PAGE });
      setRepositories(data.items);
      setTotalItems(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch repositories");
    } finally {
      setLoading(false);
    }
  };

  const handleSyncClick = async (row: RepositoryResponse) => {
    try {
      setSyncingId(row.id);
      await syncRepository(row.id);
      showToast(`Sync triggered for ${row.name}`, ToastTypeEnum.success);
      await fetchRepositories();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to sync repository");
      showToast("Failed to sync repository", ToastTypeEnum.error);
    } finally {
      setSyncingId(null);
    }
  };

  const handleInputChange = (field: keyof FormState, value: string) => {
    setFormState((prev) => ({ ...prev, [field]: value }));
  };

  const handleCreateRepository = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    // Validate provider-specific fields
    if (formState.provider === SourceControlProviderEnum.gitlab) {
      const gitlabProjectId = Number(formState.gitlab_project_id);
      if (!Number.isInteger(gitlabProjectId) || gitlabProjectId <= 0) {
        setError("GitLab project ID must be a positive integer");
        return;
      }
    } else if (formState.provider === SourceControlProviderEnum.azuredevops) {
      if (!formState.azuredevops_project_name.trim() || !formState.azuredevops_repo_id.trim()) {
        setError("Azure DevOps project name and repository ID are required");
        return;
      }
    }

    const payload: RepositoryCreatePayload = {
      provider: formState.provider,
      name: formState.name.trim(),
      path_with_namespace: formState.path_with_namespace.trim() || formState.name.trim(),
      url: formState.url.trim(),
      clone_url: formState.clone_url.trim() || formState.url.trim(),
      default_branch: formState.default_branch.trim() || "main",
    };

    // Add provider-specific fields
    if (formState.provider === SourceControlProviderEnum.gitlab) {
      payload.gitlab_project_id = Number(formState.gitlab_project_id);
    } else if (formState.provider === SourceControlProviderEnum.azuredevops) {
      payload.azuredevops_project_name = formState.azuredevops_project_name.trim();
      payload.azuredevops_repo_id = formState.azuredevops_repo_id.trim();
    }

    if (!payload.name || !payload.url) {
      setError("Name and repository URL are required fields");
      return;
    }

    try {
      setCreating(true);
      setError(null);
      const created = await createRepository(payload);
      showToast(`Repository ${created.name} created and queued for sync`, ToastTypeEnum.success);
      setFormState(initialFormState);
      setCurrentPage(1); // Reset to first page after creating
      await fetchRepositories();
      setShowForm(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create repository");
    } finally {
      setCreating(false);
    }
  };

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const showToast = useCallback((message: string, type: ToastTypeEnum = ToastTypeEnum.info) => {
    setToastMessage({ message, type });
  }, []);

  const handleToggleSelection = (id: number) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((selectedId) => selectedId !== id) : [...prev, id]
    );
  };

  const handleToggleAll = () => {
    if (selectedIds.length === repositories.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(repositories.map((repo) => repo.id));
    }
  };

  const handleDeleteClick = (repo: RepositoryResponse) => {
    setDeletingRepo(repo);
  };

  const confirmDelete = async () => {
    if (!deletingRepo) {
      return;
    }

    try {
      setDeletingInProgress(true);
      await deleteRepository(deletingRepo.id);
      showToast(`Repository "${deletingRepo.name}" deleted successfully`, ToastTypeEnum.success);
      setDeletingRepo(null);
      setSelectedIds((prev) => prev.filter((id) => id !== deletingRepo.id));
      await fetchRepositories();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete repository");
      showToast("Failed to delete repository", ToastTypeEnum.error);
    } finally {
      setDeletingInProgress(false);
    }
  };

  const handleEditClick = (repo: RepositoryResponse) => {
    setEditingRepo(repo);
    setFormState({
      provider: repo.provider,
      gitlab_project_id: repo.gitlab_project_id?.toString() || "",
      azuredevops_project_name: repo.azuredevops_project_name || "",
      azuredevops_repo_id: repo.azuredevops_repo_id || "",
      name: repo.name,
      path_with_namespace: repo.path_with_namespace,
      url: repo.url,
      clone_url: repo.clone_url,
      default_branch: repo.default_branch,
    });
    setShowForm(true);
  };

  const handleUpdateRepository = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!editingRepo) {
      return;
    }

    const payload: RepositoryUpdatePayload = {
      name: formState.name.trim(),
      path_with_namespace: formState.path_with_namespace.trim() || formState.name.trim(),
      url: formState.url.trim(),
      default_branch: formState.default_branch.trim() || "main",
    };

    if (!payload.name || !payload.url) {
      setError("Name and repository URL are required fields");
      return;
    }

    try {
      setCreating(true);
      setError(null);
      await updateRepository(editingRepo.id, payload);
      showToast(`Repository "${payload.name}" updated successfully`, ToastTypeEnum.success);
      setFormState(initialFormState);
      setEditingRepo(null);
      await fetchRepositories();
      setShowForm(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update repository");
      showToast("Failed to update repository", ToastTypeEnum.error);
    } finally {
      setCreating(false);
    }
  };

  const handleBulkSync = async () => {
    if (selectedIds.length === 0) {
      return;
    }

    try {
      setBulkOperationInProgress(true);
      const result = await bulkSyncRepositories(selectedIds);
      showToast(`Bulk sync triggered: ${result.jobs_created} jobs created`, ToastTypeEnum.success);
      setSelectedIds([]);
      await fetchRepositories();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to trigger bulk sync");
      showToast("Bulk sync failed", ToastTypeEnum.error);
    } finally {
      setBulkOperationInProgress(false);
    }
  };

  const handleBulkEnrich = async () => {
    if (selectedIds.length === 0) return;

    try {
      setBulkOperationInProgress(true);
      // Trigger for each selected repo
      let triggered = 0;
      for (const id of selectedIds) {
        await enrichmentService.triggerEnrichment(id);
        triggered++;
      }
      showToast(`Enrichment triggered for ${triggered} repositories`, ToastTypeEnum.success);
      setSelectedIds([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to trigger enrichment");
      showToast("Enrichment trigger failed", ToastTypeEnum.error);
    } finally {
      setBulkOperationInProgress(false);
    }
  };

  const handleBulkDelete = async () => {
    if (selectedIds.length === 0) {
      return;
    }

    try {
      setBulkOperationInProgress(true);
      const result = await bulkDeleteRepositories(selectedIds);
      showToast(`Bulk delete completed: ${result.removed_count} repositories deleted`, ToastTypeEnum.success);
      setSelectedIds([]);
      setShowBulkDeleteConfirm(false);
      await fetchRepositories();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete repositories");
      showToast("Bulk delete failed", ToastTypeEnum.error);
    } finally {
      setBulkOperationInProgress(false);
    }
  };

  const cancelEdit = () => {
    setEditingRepo(null);
    setFormState(initialFormState);
    setShowForm(false);
  };

  if (loading) {
    return (
      <div className={styles.repositories_container}>
        <div className={styles.loading_message}>Loading repositories...</div>
      </div>
    );
  }

  return (
    <div className={styles.repositories_container}>
      <div className={styles.repositories_header}>
        <div>
          <h1 className={styles.repositories_title}>Repositories</h1>
          <p className={styles.repositories_subtitle}>
            {activeRepositoryCount} active repositories tracked
            {selectedIds.length > 0 && ` • ${selectedIds.length} selected`}
          </p>
        </div>
        <div className={styles.repositories_actions}>
          {selectedIds.length > 0 && (
            <>
              <button
                className={styles.primary_button}
                onClick={handleBulkSync}
                disabled={bulkOperationInProgress}
              >
                Sync Selected ({selectedIds.length})
              </button>
              <button
                className={styles.primary_button}
                onClick={handleBulkEnrich}
                disabled={bulkOperationInProgress}
              >
                Enrich Selected ({selectedIds.length})
              </button>
              <button
                className={styles.danger_button}
                onClick={() => setShowBulkDeleteConfirm(true)}
                disabled={bulkOperationInProgress}
              >
                Delete Selected ({selectedIds.length})
              </button>
            </>
          )}
          <button className={styles.secondary_button} onClick={() => setShowGitLabDiscoveryModal(true)}>
            Discover from GitLab
          </button>
          <button className={styles.secondary_button} onClick={() => setShowAzureDevOpsDiscoveryModal(true)}>
            Discover from Azure DevOps
          </button>
          <button className={styles.secondary_button} onClick={() => {
            setEditingRepo(null);
            setFormState(initialFormState);
            setShowForm((prev) => !prev);
          }}>
            {showForm ? "Close" : "Add Repository"}
          </button>
          <button className={styles.refresh_button} onClick={fetchRepositories} disabled={syncingId !== null}>
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className={styles.error_banner}>
          <strong>Error:</strong> {error}
          <button className={styles.dismiss_button} onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      )}

      {showForm && (
        <section className={styles.form_panel}>
          <h2 className={styles.form_title}>{editingRepo ? "Edit Repository" : "Create Repository"}</h2>
          <form className={styles.repository_form} onSubmit={editingRepo ? handleUpdateRepository : handleCreateRepository}>
            {!editingRepo && (
              <div className={styles.form_row}>
                <label className={styles.form_label} htmlFor="provider">
                  Source Control Provider
                </label>
                <select
                  id="provider"
                  name="provider"
                  className={styles.form_input}
                  value={formState.provider}
                  onChange={(event) => handleInputChange("provider", event.target.value)}
                  required
                >
                  <option value={SourceControlProviderEnum.gitlab}>GitLab</option>
                  <option value={SourceControlProviderEnum.azuredevops}>Azure DevOps</option>
                </select>
              </div>
            )}

            {formState.provider === SourceControlProviderEnum.gitlab && (
              <div className={styles.form_row}>
                <label className={styles.form_label} htmlFor="gitlab_project_id">
                  GitLab Project ID
                </label>
                <input
                  id="gitlab_project_id"
                  name="gitlab_project_id"
                  className={styles.form_input}
                  value={formState.gitlab_project_id}
                  onChange={(event) => handleInputChange("gitlab_project_id", event.target.value)}
                  placeholder="e.g. 123456"
                  required={formState.provider === SourceControlProviderEnum.gitlab}
                />
              </div>
            )}

            {formState.provider === SourceControlProviderEnum.azuredevops && (
              <>
                <div className={styles.form_row}>
                  <label className={styles.form_label} htmlFor="azuredevops_project_name">
                    Azure DevOps Project Name
                  </label>
                  <input
                    id="azuredevops_project_name"
                    name="azuredevops_project_name"
                    className={styles.form_input}
                    value={formState.azuredevops_project_name}
                    onChange={(event) => handleInputChange("azuredevops_project_name", event.target.value)}
                    placeholder="e.g. MyProject"
                    required={formState.provider === SourceControlProviderEnum.azuredevops}
                  />
                </div>
                <div className={styles.form_row}>
                  <label className={styles.form_label} htmlFor="azuredevops_repo_id">
                    Azure DevOps Repository ID
                  </label>
                  <input
                    id="azuredevops_repo_id"
                    name="azuredevops_repo_id"
                    className={styles.form_input}
                    value={formState.azuredevops_repo_id}
                    onChange={(event) => handleInputChange("azuredevops_repo_id", event.target.value)}
                    placeholder="e.g. repo-guid-here"
                    required={formState.provider === SourceControlProviderEnum.azuredevops}
                  />
                </div>
              </>
            )}

            <div className={styles.form_row}>
              <label className={styles.form_label} htmlFor="name">
                Name
              </label>
              <input
                id="name"
                name="name"
                className={styles.form_input}
                value={formState.name}
                onChange={(event) => handleInputChange("name", event.target.value)}
                placeholder="Repository display name"
                required
              />
            </div>

            <div className={styles.form_row}>
              <label className={styles.form_label} htmlFor="path_with_namespace">
                Path with Namespace
              </label>
              <input
                id="path_with_namespace"
                name="path_with_namespace"
                className={styles.form_input}
                value={formState.path_with_namespace}
                onChange={(event) => handleInputChange("path_with_namespace", event.target.value)}
                placeholder="group/project"
              />
              <p className={styles.field_hint}>
                Defaults to the repository name when left blank.
              </p>
            </div>

            <div className={styles.form_row}>
              <label className={styles.form_label} htmlFor="url">
                Repository URL
              </label>
              <input
                id="url"
                name="url"
                className={styles.form_input}
                value={formState.url}
                onChange={(event) => handleInputChange("url", event.target.value)}
                placeholder="https://gitlab.example.com/group/project.git"
                required
              />
            </div>

            <div className={styles.form_row}>
              <label className={styles.form_label} htmlFor="default_branch">
                Default Branch
              </label>
              <input
                id="default_branch"
                name="default_branch"
                className={styles.form_input}
                value={formState.default_branch}
                onChange={(event) => handleInputChange("default_branch", event.target.value)}
                placeholder="main"
              />
            </div>

            <div className={styles.form_actions}>
              <button className={styles.secondary_button} type="button" onClick={editingRepo ? cancelEdit : () => setShowForm(false)}>
                Cancel
              </button>
              <button className={styles.primary_button} type="submit" disabled={creating}>
                {creating ? (editingRepo ? "Updating..." : "Creating...") : (editingRepo ? "Update Repository" : "Create Repository")}
              </button>
            </div>
          </form>
        </section>
      )}

      {repositories.length === 0 ? (
        <div className={styles.empty_state}>
          <p>No repositories found.</p>
          <p className={styles.empty_state_hint}>
            Repositories will appear here once they are synced from GitLab.
          </p>
        </div>
      ) : (
        <>
          <RepoTable
            rows={repositories}
            on_sync_click={handleSyncClick}
            on_delete_click={handleDeleteClick}
            on_edit_click={handleEditClick}
            selectedIds={selectedIds}
            onToggleSelection={handleToggleSelection}
            onToggleAll={handleToggleAll}
          />
          <Pagination
            currentPage={currentPage}
            totalPages={Math.ceil(totalItems / ITEMS_PER_PAGE)}
            onPageChange={handlePageChange}
            totalItems={totalItems}
            itemsPerPage={ITEMS_PER_PAGE}
          />
        </>
      )}

      {syncingId !== null && (
        <div className={styles.syncing_overlay}>Sync queued for repository #{syncingId}</div>
      )}

      {toastMessage && (
        <Toast
          message={toastMessage.message}
          type={toastMessage.type}
          onClose={() => setToastMessage(null)}
        />
      )}

      <ConfirmationModal
        isOpen={deletingRepo !== null}
        title="Delete Repository"
        message={
          <div>
            <p>Are you sure you want to delete <strong>{deletingRepo?.name}</strong>?</p>
            <p>This action cannot be undone. All associated data including files, symbols, and embeddings will be permanently deleted.</p>
          </div>
        }
        confirmText="Delete Repository"
        variant="danger"
        onConfirm={confirmDelete}
        onCancel={() => setDeletingRepo(null)}
        isLoading={deletingInProgress}
      />

      <ConfirmationModal
        isOpen={showBulkDeleteConfirm}
        title="Bulk Delete Repositories"
        message={
          <div>
            <p>Are you sure you want to delete <strong>{selectedIds.length} repositories</strong>?</p>
            <p>This action cannot be undone. All associated data will be permanently deleted.</p>
          </div>
        }
        confirmText={`Delete ${selectedIds.length} Repositories`}
        variant="danger"
        onConfirm={handleBulkDelete}
        onCancel={() => setShowBulkDeleteConfirm(false)}
        isLoading={bulkOperationInProgress}
      />

      <GitLabDiscoveryModal
        isOpen={showGitLabDiscoveryModal}
        onClose={() => setShowGitLabDiscoveryModal(false)}
        onSuccess={() => {
          void fetchRepositories();
          showToast("Repositories updated successfully", ToastTypeEnum.success);
        }}
      />

      <AzureDevOpsDiscoveryModal
        isOpen={showAzureDevOpsDiscoveryModal}
        onClose={() => setShowAzureDevOpsDiscoveryModal(false)}
        onSuccess={() => {
          void fetchRepositories();
          showToast("Repositories updated successfully", ToastTypeEnum.success);
        }}
      />
    </div>
  );
}


