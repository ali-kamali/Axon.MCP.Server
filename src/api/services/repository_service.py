"""Repository service utilities."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.repositories import (
    RepositoryCreate,
    RepositoryResponse,
    RepositorySyncResponse,
    GitLabProjectDiscovery,
    GitLabDiscoveryResponse,
    AzureDevOpsRepositoryDiscovery,
    AzureDevOpsDiscoveryResponse,
    BulkRepositoryAddResponse,
    BulkRepositoryRemoveResponse,
    BulkRepositorySyncResponse,
    CommitInfo,
)
from src.config.enums import RepositoryStatusEnum, SourceControlProviderEnum
from src.database.models import Repository, File, Commit
from src.gitlab.client import GitLabClient
from src.azuredevops.client import AzureDevOpsClient
from src.utils.logging_config import get_logger
from src.workers.tasks import sync_repository


logger = get_logger(__name__)


class RepositoryService:
    """Encapsulates repository CRUD and sync operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self, *, offset: int, limit: int) -> Tuple[List[RepositoryResponse], int]:
        """List repositories with total count."""
        # Get total count
        count_stmt = select(func.count()).select_from(Repository)
        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar() or 0
        
        # Get paginated items
        stmt: Select = select(Repository).offset(offset).limit(limit).order_by(Repository.updated_at.desc())
        result = await self._session.execute(stmt)
        repositories = result.scalars().all()
        
        # Add helpful URLs and extra info to each repository
        responses = []
        for repo in repositories:
            response = RepositoryResponse.model_validate(repo)
            response.search_url = f"/api/search?repository_id={repo.id}"
            response.sync_url = f"/api/repositories/{repo.id}/sync"
            
            # Enrich with language stats and commit info
            await self._enrich_repository_response(response)
            
            responses.append(response)
        
        return responses, total

    async def get(self, repository_id: int) -> Optional[RepositoryResponse]:
        repo = await self._session.get(Repository, repository_id)
        if repo is None:
            return None
        response = RepositoryResponse.model_validate(repo)
        # Add helpful URLs
        response.search_url = f"/api/search?repository_id={repo.id}"
        response.sync_url = f"/api/repositories/{repo.id}/sync"
        
        # Enrich with language stats and commit info
        await self._enrich_repository_response(response)
        
        return response

    async def _enrich_repository_response(self, response: RepositoryResponse) -> None:
        """Populate language stats and last commit info."""
        # Get language stats
        stmt = select(File.language, func.sum(File.size_bytes)).where(File.repository_id == response.id).group_by(File.language)
        result = await self._session.execute(stmt)
        stats = result.all()
        
        total_size = sum((size for _, size in stats if size is not None), 0)
        if total_size > 0:
            response.languages = {lang.value: (size / total_size) * 100 for lang, size in stats if size is not None}
            # Find primary language
            if stats:
                primary = max(stats, key=lambda x: x[1] or 0)
                response.primary_language = primary[0].value
            
        # Get last commit
        stmt = select(Commit).where(Commit.repository_id == response.id).order_by(Commit.committed_date.desc()).limit(1)
        result = await self._session.execute(stmt)
        commit = result.scalar_one_or_none()
        
        if commit:
            response.last_commit = CommitInfo(
                sha=commit.sha,
                message=commit.message,
                author_name=commit.author_name,
                committed_date=commit.committed_date
            )

    async def create(self, payload: RepositoryCreate) -> RepositoryResponse:
        repository = Repository(
            provider=payload.provider,
            gitlab_project_id=payload.gitlab_project_id,
            azuredevops_project_name=payload.azuredevops_project_name,
            azuredevops_repo_id=payload.azuredevops_repo_id,
            name=payload.name,
            path_with_namespace=payload.path_with_namespace,
            url=payload.url,
            clone_url=payload.clone_url,
            default_branch=payload.default_branch,
            status=RepositoryStatusEnum.PENDING,
        )

        self._session.add(repository)
        try:
            await self._session.flush()
            await self._session.refresh(repository)
        except IntegrityError as exc:  # noqa: BLE001
            error_msg = f"Failed to create repository: {str(exc)}"
            logger.warning(
                "repository_create_conflict",
                provider=payload.provider,
                gitlab_project_id=payload.gitlab_project_id,
                azuredevops_project_name=payload.azuredevops_project_name,
                azuredevops_repo_id=payload.azuredevops_repo_id,
                path_with_namespace=payload.path_with_namespace,
                error=error_msg,
            )
            raise
        logger.info("repository_created", repository_id=repository.id)
        return RepositoryResponse.model_validate(repository)

    async def trigger_sync(self, repository_id: int) -> RepositorySyncResponse:
        repository = await self._session.get(Repository, repository_id)
        if repository is None:
            raise ValueError(f"Failed to trigger sync: Repository with ID {repository_id} not found")

        repository.status = RepositoryStatusEnum.PENDING
        repository.last_synced_at = datetime.utcnow()
        await self._session.flush()

        # Trigger Celery task for background sync
        task = sync_repository.delay(repository_id)
        
        logger.info("repository_sync_enqueued", repository_id=repository_id, task_id=task.id)
        return RepositorySyncResponse(
            repository_id=repository_id,
            status="queued",
            task_id=task.id,
            message="Sync scheduled"
        )

    async def discover_gitlab_projects(self, group_id: str) -> GitLabDiscoveryResponse:
        """
        Discover all projects in a GitLab group and check tracking status.

        Args:
            group_id: GitLab group ID or path

        Returns:
            Discovery response with projects and tracking status
        """
        # Get all projects from GitLab
        gitlab_client = GitLabClient()
        gitlab_projects = gitlab_client.list_group_projects(group_id)

        # Get all tracked GitLab repositories
        stmt = select(Repository).where(Repository.provider == SourceControlProviderEnum.GITLAB)
        result = await self._session.execute(stmt)
        tracked_repos = {repo.gitlab_project_id: repo for repo in result.scalars().all()}

        # Build discovery response
        projects: List[GitLabProjectDiscovery] = []
        tracked_count = 0
        untracked_count = 0

        for project in gitlab_projects:
            gitlab_id = project["id"]
            is_tracked = gitlab_id in tracked_repos
            tracked_repo = tracked_repos.get(gitlab_id)

            if is_tracked:
                tracked_count += 1
            else:
                untracked_count += 1

            projects.append(
                GitLabProjectDiscovery(
                    gitlab_project_id=gitlab_id,
                    name=project["name"],
                    path_with_namespace=project["path_with_namespace"],
                    url=project["http_url_to_repo"],
                    default_branch=project["default_branch"],
                    description=project.get("description"),
                    visibility=project.get("visibility"),
                    is_tracked=is_tracked,
                    tracked_repository_id=tracked_repo.id if tracked_repo else None,
                )
            )

        logger.info(
            "gitlab_projects_discovered",
            group_id=group_id,
            total=len(projects),
            tracked=tracked_count,
            untracked=untracked_count,
        )

        return GitLabDiscoveryResponse(
            group_id=group_id,
            total_projects=len(projects),
            tracked_count=tracked_count,
            untracked_count=untracked_count,
            projects=projects,
        )

    async def discover_azuredevops_repositories(self, project_name: str) -> AzureDevOpsDiscoveryResponse:
        """
        Discover all repositories in an Azure DevOps project and check tracking status.

        Args:
            project_name: Azure DevOps project name

        Returns:
            Discovery response with repositories and tracking status
        """
        # Get all repositories from Azure DevOps
        azuredevops_client = AzureDevOpsClient()
        azuredevops_repos = azuredevops_client.list_project_repositories(project_name)

        # Get all tracked Azure DevOps repositories
        stmt = select(Repository).where(Repository.provider == SourceControlProviderEnum.AZUREDEVOPS)
        result = await self._session.execute(stmt)
        tracked_repos = {
            (repo.azuredevops_project_name, repo.azuredevops_repo_id): repo 
            for repo in result.scalars().all()
        }

        # Build discovery response
        repositories: List[AzureDevOpsRepositoryDiscovery] = []
        tracked_count = 0
        untracked_count = 0

        for repo in azuredevops_repos:
            repo_key = (project_name, repo["id"])
            is_tracked = repo_key in tracked_repos
            tracked_repo = tracked_repos.get(repo_key)

            if is_tracked:
                tracked_count += 1
            else:
                untracked_count += 1

            repositories.append(
                AzureDevOpsRepositoryDiscovery(
                    azuredevops_project_name=project_name,
                    azuredevops_repo_id=repo["id"],
                    name=repo["name"],
                    path_with_namespace=repo["path_with_namespace"],
                    url=repo["url"],
                    clone_url=repo["clone_url"],
                    default_branch=repo["default_branch"],
                    size=repo["size"],
                    is_fork=repo["is_fork"],
                    is_disabled=repo["is_disabled"],
                    is_tracked=is_tracked,
                    tracked_repository_id=tracked_repo.id if tracked_repo else None,
                )
            )

        logger.info(
            "azuredevops_repositories_discovered",
            project_name=project_name,
            total=len(repositories),
            tracked=tracked_count,
            untracked=untracked_count,
        )

        return AzureDevOpsDiscoveryResponse(
            project_name=project_name,
            total_repositories=len(repositories),
            tracked_count=tracked_count,
            untracked_count=untracked_count,
            repositories=repositories,
        )

    async def bulk_add_repositories(
        self, repositories: List[RepositoryCreate]
    ) -> BulkRepositoryAddResponse:
        """
        Add multiple repositories in bulk.

        Args:
            repositories: List of repository creation payloads

        Returns:
            Bulk operation response
        """
        added_count = 0
        skipped_count = 0
        failed_count = 0
        added_repository_ids: List[int] = []
        errors: List[str] = []

        for repo_data in repositories:
            try:
                # Check if already exists based on provider
                if repo_data.provider == SourceControlProviderEnum.GITLAB:
                    stmt = select(Repository).where(
                        Repository.provider == SourceControlProviderEnum.GITLAB,
                        Repository.gitlab_project_id == repo_data.gitlab_project_id
                    )
                elif repo_data.provider == SourceControlProviderEnum.AZUREDEVOPS:
                    stmt = select(Repository).where(
                        Repository.provider == SourceControlProviderEnum.AZUREDEVOPS,
                        Repository.azuredevops_project_name == repo_data.azuredevops_project_name,
                        Repository.azuredevops_repo_id == repo_data.azuredevops_repo_id
                    )
                else:
                    raise ValueError(f"Unsupported provider: {repo_data.provider}")

                result = await self._session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    skipped_count += 1
                    logger.info(
                        "repository_already_exists",
                        provider=repo_data.provider,
                        gitlab_project_id=repo_data.gitlab_project_id,
                        azuredevops_project_name=repo_data.azuredevops_project_name,
                        azuredevops_repo_id=repo_data.azuredevops_repo_id,
                        repository_id=existing.id,
                    )
                    continue

                # Determine optimal branch using priority rules
                try:
                    if repo_data.provider == SourceControlProviderEnum.GITLAB:
                        gitlab_client = GitLabClient()
                        optimal_branch = gitlab_client.get_optimal_branch_for_project(
                            repo_data.gitlab_project_id
                        )
                    elif repo_data.provider == SourceControlProviderEnum.AZUREDEVOPS:
                        azuredevops_client = AzureDevOpsClient()
                        optimal_branch = azuredevops_client.get_optimal_branch_for_repository(
                            repo_data.azuredevops_project_name, 
                            repo_data.name
                        )
                    else:
                        optimal_branch = repo_data.default_branch
                        
                    logger.info(
                        "optimal_branch_determined",
                        provider=repo_data.provider,
                        gitlab_project_id=repo_data.gitlab_project_id,
                        azuredevops_project_name=repo_data.azuredevops_project_name,
                        azuredevops_repo_id=repo_data.azuredevops_repo_id,
                        optimal_branch=optimal_branch,
                        provided_branch=repo_data.default_branch
                    )
                except Exception as e:  # noqa: BLE001
                    # Fallback to provided branch if optimization fails
                    optimal_branch = repo_data.default_branch
                    logger.warning(
                        "optimal_branch_fallback",
                        provider=repo_data.provider,
                        gitlab_project_id=repo_data.gitlab_project_id,
                        azuredevops_project_name=repo_data.azuredevops_project_name,
                        azuredevops_repo_id=repo_data.azuredevops_repo_id,
                        error=str(e)
                    )

                # Create new repository
                repository = Repository(
                    provider=repo_data.provider,
                    gitlab_project_id=repo_data.gitlab_project_id,
                    azuredevops_project_name=repo_data.azuredevops_project_name,
                    azuredevops_repo_id=repo_data.azuredevops_repo_id,
                    name=repo_data.name,
                    path_with_namespace=repo_data.path_with_namespace,
                    url=repo_data.url,
                    clone_url=repo_data.clone_url,
                    default_branch=optimal_branch,
                    status=RepositoryStatusEnum.PENDING,
                )

                self._session.add(repository)
                await self._session.flush()
                await self._session.refresh(repository)

                added_repository_ids.append(repository.id)
                added_count += 1

                logger.info(
                    "repository_bulk_added",
                    repository_id=repository.id,
                    provider=repo_data.provider,
                    gitlab_project_id=repo_data.gitlab_project_id,
                    azuredevops_project_name=repo_data.azuredevops_project_name,
                    azuredevops_repo_id=repo_data.azuredevops_repo_id,
                )

            except Exception as e:
                failed_count += 1
                error_msg = f"Failed to add repository {repo_data.path_with_namespace}: {str(e)}"
                errors.append(error_msg)
                logger.error(
                    "repository_bulk_add_failed",
                    path_with_namespace=repo_data.path_with_namespace,
                    error=error_msg,
                )

        # Trigger Celery sync tasks for all newly added repositories
        if added_count > 0:
            for repo_id in added_repository_ids:
                try:
                    task = sync_repository.delay(repo_id)
                    logger.info(
                        "repository_sync_triggered_bulk",
                        repository_id=repo_id,
                        task_id=task.id
                    )
                except Exception as e:
                    error_msg = f"Failed to trigger sync for repository: {str(e)}"
                    logger.error(
                        "repository_sync_trigger_failed",
                        repository_id=repo_id,
                        error=error_msg
                    )

        logger.info(
            "bulk_add_completed",
            added=added_count,
            skipped=skipped_count,
            failed=failed_count,
        )

        return BulkRepositoryAddResponse(
            added_count=added_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
            added_repository_ids=added_repository_ids,
            errors=errors,
        )

    async def bulk_remove_repositories(
        self, repository_ids: List[int]
    ) -> BulkRepositoryRemoveResponse:
        """
        Remove multiple repositories in bulk.

        Args:
            repository_ids: List of repository IDs to remove

        Returns:
            Bulk operation response
        """
        removed_count = 0
        failed_count = 0
        errors: List[str] = []

        for repo_id in repository_ids:
            try:
                repository = await self._session.get(Repository, repo_id)
                if repository is None:
                    failed_count += 1
                    errors.append(f"Failed to remove repository: Repository with ID {repo_id} not found")
                    continue

                await self._session.delete(repository)
                removed_count += 1

                logger.info("repository_bulk_removed", repository_id=repo_id)

            except Exception as e:
                failed_count += 1
                error_msg = f"Failed to remove repository {repo_id}: {str(e)}"
                errors.append(error_msg)
                logger.error("repository_bulk_remove_failed", repository_id=repo_id, error=error_msg)

        logger.info("bulk_remove_completed", removed=removed_count, failed=failed_count)

        return BulkRepositoryRemoveResponse(
            removed_count=removed_count, failed_count=failed_count, errors=errors
        )

    async def bulk_sync_repositories(
        self, repository_ids: List[int]
    ) -> BulkRepositorySyncResponse:
        """
        Sync multiple repositories in bulk.

        Args:
            repository_ids: List of repository IDs to sync

        Returns:
            Bulk sync response with job IDs
        """
        jobs_created = 0
        failed_count = 0
        job_ids: List[str] = []
        errors: List[str] = []

        for repo_id in repository_ids:
            try:
                repository = await self._session.get(Repository, repo_id)
                if repository is None:
                    failed_count += 1
                    errors.append(f"Failed to sync repository: Repository with ID {repo_id} not found")
                    continue

                # Update repository status and last_synced_at
                repository.status = RepositoryStatusEnum.PENDING
                repository.last_synced_at = datetime.utcnow()
                await self._session.flush()

                # Trigger Celery task for background sync
                task = sync_repository.delay(repo_id)
                job_ids.append(task.id)
                jobs_created += 1

                logger.info(
                    "repository_sync_enqueued_bulk",
                    repository_id=repo_id,
                    task_id=task.id
                )

            except Exception as e:
                failed_count += 1
                error_msg = f"Failed to sync repository {repo_id}: {str(e)}"
                errors.append(error_msg)
                logger.error("repository_bulk_sync_failed", repository_id=repo_id, error=error_msg)

        logger.info("bulk_sync_completed", jobs_created=jobs_created, failed=failed_count)

        return BulkRepositorySyncResponse(
            jobs_created=jobs_created,
            job_ids=job_ids,
            failed_count=failed_count,
            errors=errors,
        )


