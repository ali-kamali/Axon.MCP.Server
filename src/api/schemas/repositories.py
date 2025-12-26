"""Pydantic schemas for repository endpoints."""

from datetime import datetime
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict

from src.config.enums import RepositoryStatusEnum, SourceControlProviderEnum

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper."""

    items: list[T]
    total: int
    limit: int
    offset: int


class RepositoryBase(BaseModel):
    """Shared repository attributes."""

    provider: SourceControlProviderEnum
    name: str
    path_with_namespace: str
    url: str
    clone_url: str
    default_branch: str
    
    # Provider-specific fields (optional)
    gitlab_project_id: Optional[int] = None
    azuredevops_project_name: Optional[str] = None
    azuredevops_repo_id: Optional[str] = None


class RepositoryCreate(BaseModel):
    """Request body for repository creation or sync."""

    provider: SourceControlProviderEnum
    name: str
    path_with_namespace: str
    url: str
    clone_url: str
    default_branch: str = "main"
    
    # Provider-specific fields (optional)
    gitlab_project_id: Optional[int] = None
    azuredevops_project_name: Optional[str] = None
    azuredevops_repo_id: Optional[str] = None


class RepositoryResponse(BaseModel):
    """Response model for repository resources."""

    model_config = ConfigDict(from_attributes=True)

    # Primary identifier
    id: int  # Use with search filters, get_file_content, etc.
    
    # Repository info
    provider: SourceControlProviderEnum
    name: str
    path_with_namespace: str
    url: str
    clone_url: str
    default_branch: str
    
    # Status and statistics
    status: RepositoryStatusEnum
    last_synced_at: Optional[datetime] = None
    last_commit_sha: Optional[str] = None
    total_files: int
    total_symbols: int
    size_bytes: int
    
    # Enhanced statistics
    languages: dict[str, float] = {}  # Language distribution by percentage
    primary_language: Optional[str] = None
    
    # Last commit info
    last_commit: Optional["CommitInfo"] = None
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    
    # Provider-specific fields (optional)
    gitlab_project_id: Optional[int] = None
    azuredevops_project_name: Optional[str] = None
    azuredevops_repo_id: Optional[str] = None
    
    # Helpful URLs for related operations (computed)
    search_url: Optional[str] = None  # URL to search this repository
    sync_url: Optional[str] = None  # URL to trigger sync


class CommitInfo(BaseModel):
    """Brief commit information."""
    
    sha: str
    message: str
    author_name: Optional[str] = None
    committed_date: Optional[datetime] = None


class RepositorySyncResponse(BaseModel):
    """Response for repository sync trigger."""

    repository_id: int
    status: str
    task_id: Optional[str] = None
    message: Optional[str] = None


class GitLabProjectDiscovery(BaseModel):
    """GitLab project from discovery with tracking status."""

    gitlab_project_id: int
    name: str
    path_with_namespace: str
    url: str
    default_branch: str
    description: Optional[str] = None
    visibility: Optional[str] = None
    is_tracked: bool
    tracked_repository_id: Optional[int] = None


class GitLabDiscoveryResponse(BaseModel):
    """Response for GitLab group discovery."""

    group_id: str
    total_projects: int
    tracked_count: int
    untracked_count: int
    projects: list[GitLabProjectDiscovery]


class AzureDevOpsRepositoryDiscovery(BaseModel):
    """Azure DevOps repository from discovery with tracking status."""

    azuredevops_project_name: str
    azuredevops_repo_id: str
    name: str
    path_with_namespace: str
    url: str
    clone_url: str
    default_branch: str
    size: int
    is_fork: bool
    is_disabled: bool
    is_tracked: bool
    tracked_repository_id: Optional[int] = None


class AzureDevOpsDiscoveryResponse(BaseModel):
    """Response for Azure DevOps project discovery."""

    project_name: str
    total_repositories: int
    tracked_count: int
    untracked_count: int
    repositories: list[AzureDevOpsRepositoryDiscovery]


class BulkRepositoryAddRequest(BaseModel):
    """Request to add multiple repositories."""

    repositories: list[RepositoryCreate]


class BulkRepositoryAddResponse(BaseModel):
    """Response for bulk repository addition."""

    added_count: int
    skipped_count: int
    failed_count: int
    added_repository_ids: list[int]
    errors: list[str]


class BulkRepositoryRemoveRequest(BaseModel):
    """Request to remove multiple repositories."""

    repository_ids: list[int]


class BulkRepositoryRemoveResponse(BaseModel):
    """Response for bulk repository removal."""

    removed_count: int
    failed_count: int
    errors: list[str]


class BulkRepositorySyncRequest(BaseModel):
    """Request to sync multiple repositories."""

    repository_ids: list[int]


class BulkRepositorySyncResponse(BaseModel):
    """Response for bulk repository sync."""

    jobs_created: int
    job_ids: list[str]
    failed_count: int
    errors: list[str]


