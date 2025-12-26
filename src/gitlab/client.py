import gitlab
from typing import List, Dict, Optional

from src.config.settings import settings
from src.utils.logging_config import get_logger


logger = get_logger(__name__)


class GitLabClient:
    """GitLab API client wrapper with authentication and error handling."""

    def __init__(self, token: Optional[str] = None, url: Optional[str] = None) -> None:
        """
        Initialize GitLab client.

        Args:
            token: GitLab personal access token (defaults to settings)
            url: GitLab URL (defaults to settings)
        """
        self.url = url or settings.gitlab_url
        self.token = token or settings.gitlab_token

        try:
            self.client = gitlab.Gitlab(url=self.url, private_token=self.token)
            self.client.auth()
            logger.info("gitlab_client_initialized", url=self.url)
        except gitlab.exceptions.GitlabAuthenticationError as e:  # type: ignore[attr-defined]
            error_msg = f"Failed to authenticate with GitLab: {str(e)}"
            logger.error("gitlab_authentication_failed", error=error_msg)
            raise

    def _determine_default_branch(self, project) -> str:
        """
        Determine the default branch to use based on priority rules.
        
        Priority:
        1. "prd" branch if it exists
        2. "production" branch if it exists
        3. Project's default branch
        
        Args:
            project: GitLab project object
            
        Returns:
            Branch name to use
        """
        try:
            # Get list of branches
            branches = project.branches.list(all=True)
            branch_names = {branch.name for branch in branches}
            
            # Check priority order
            if "prd" in branch_names:
                logger.info(
                    "branch_priority_selected",
                    project_id=project.id,
                    selected_branch="prd",
                    reason="prd_branch_exists"
                )
                return "prd"
            elif "production" in branch_names:
                logger.info(
                    "branch_priority_selected",
                    project_id=project.id,
                    selected_branch="production",
                    reason="production_branch_exists"
                )
                return "production"
            else:
                # Use project default branch
                default = project.default_branch or "main"
                logger.info(
                    "branch_priority_selected",
                    project_id=project.id,
                    selected_branch=default,
                    reason="using_project_default"
                )
                return default
        except Exception as e:  # noqa: BLE001
            # If we can't get branches, fallback to project default
            error_msg = f"Failed to list branches, using default: {str(e)}"
            logger.warning(
                "branch_list_failed_fallback",
                project_id=project.id,
                error=error_msg
            )
            return project.default_branch or "main"

    def get_project(self, project_id: int) -> Dict:
        """
        Get project details by ID.

        Args:
            project_id: GitLab project ID

        Returns:
            Project metadata dictionary
        """
        try:
            project = self.client.projects.get(project_id)
            default_branch = self._determine_default_branch(project)
            
            return {
                "id": project.id,
                "name": project.name,
                "path_with_namespace": project.path_with_namespace,
                "http_url_to_repo": project.http_url_to_repo,
                "default_branch": default_branch,
                "description": project.description,
                "visibility": project.visibility,
                "created_at": project.created_at,
                "last_activity_at": project.last_activity_at,
                "archived": project.archived,
            }
        except gitlab.exceptions.GitlabGetError as e:  # type: ignore[attr-defined]
            error_msg = f"Failed to get GitLab project: {str(e)}"
            logger.error("gitlab_project_get_failed", project_id=project_id, error=error_msg)
            raise

    def list_group_projects(self, group_id: str) -> List[Dict]:
        """
        List all projects in a GitLab group.

        Args:
            group_id: GitLab group ID or path

        Returns:
            List of project metadata dictionaries
        """
        try:
            group = self.client.groups.get(group_id)
            projects = group.projects.list(all=True, include_subgroups=True)

            result = []
            for project in projects:
                if project.attributes.get("archived", False):
                    continue
                
                # For list operations, use a lightweight approach:
                # Get branch info only if it's cached or use default
                # This avoids N API calls for N projects
                default_branch = project.attributes.get("default_branch", "main")
                
                # Try to determine priority branch efficiently
                # Note: group.projects.list() doesn't include branches, 
                # so we use the project's default_branch for listing
                # The full branch priority logic will apply when actually cloning
                result.append({
                    "id": project.id,
                    "name": project.name,
                    "path_with_namespace": project.path_with_namespace,
                    "http_url_to_repo": project.http_url_to_repo,
                    "default_branch": default_branch,
                    "description": project.description,
                    "visibility": project.attributes.get("visibility"),
                })
            
            return result
        except gitlab.exceptions.GitlabGetError as e:  # type: ignore[attr-defined]
            error_msg = f"Failed to list GitLab group projects: {str(e)}"
            logger.error("gitlab_group_list_failed", group_id=group_id, error=error_msg)
            raise

    def get_latest_commit(self, project_id: int, branch: str | None = None) -> Dict:
        """
        Get latest commit for a branch.

        Args:
            project_id: GitLab project ID
            branch: Branch name (defaults to default_branch)

        Returns:
            Commit metadata dictionary
        """
        try:
            project = self.client.projects.get(project_id)
            ref = branch or project.default_branch
            commits = project.commits.list(ref_name=ref, per_page=1)

            if not commits:
                return {}

            commit = commits[0]
            return {
                "sha": commit.id,
                "message": commit.message,
                "author_name": commit.author_name,
                "author_email": commit.author_email,
                "committed_date": commit.committed_date,
                "title": commit.title,
            }
        except gitlab.exceptions.GitlabGetError as e:  # type: ignore[attr-defined]
            error_msg = f"Failed to get GitLab commit: {str(e)}"
            logger.error(
                "gitlab_commit_get_failed",
                project_id=project_id,
                branch=branch,
                error=error_msg,
            )
            raise

    def list_project_files(
        self,
        project_id: int,
        path: str = "",
        ref: str | None = None,
        recursive: bool = True,
    ) -> List[Dict]:
        """
        List files in a project repository.

        Args:
            project_id: GitLab project ID
            path: Directory path to list
            ref: Git ref (branch/tag/commit)
            recursive: Whether to list recursively

        Returns:
            List of file metadata dictionaries
        """
        try:
            project = self.client.projects.get(project_id)
            ref = ref or project.default_branch

            files = project.repository_tree(
                path=path,
                ref=ref,
                recursive=recursive,
                all=True,
            )

            return [
                {
                    "path": file["path"],
                    "name": file["name"],
                    "type": file["type"],
                    "mode": file["mode"],
                }
                for file in files
                if file["type"] == "blob"
            ]
        except gitlab.exceptions.GitlabGetError as e:  # type: ignore[attr-defined]
            error_msg = f"Failed to list GitLab project files: {str(e)}"
            logger.error(
                "gitlab_files_list_failed",
                project_id=project_id,
                path=path,
                error=error_msg,
            )
            raise

    def get_optimal_branch_for_project(self, project_id: int) -> str:
        """
        Get the optimal branch for a project using priority rules.
        
        This is a convenience method that fetches the project and determines
        the best branch to use based on priority rules.
        
        Args:
            project_id: GitLab project ID
            
        Returns:
            Branch name to use
        """
        try:
            project = self.client.projects.get(project_id)
            return self._determine_default_branch(project)
        except Exception as e:  # noqa: BLE001
            error_msg = f"Failed to determine optimal branch: {str(e)}"
            logger.error(
                "optimal_branch_determination_failed",
                project_id=project_id,
                error=error_msg
            )
            # Fallback to asking for project default
            try:
                project = self.client.projects.get(project_id)
                return project.default_branch or "main"
            except Exception:  # noqa: BLE001
                return "main"

    def test_connection(self) -> bool:
        """
        Test GitLab connection and authentication.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.client.user
            logger.info("gitlab_connection_test_successful")
            return True
        except Exception as e:  # noqa: BLE001
            error_msg = f"Failed to test GitLab connection: {str(e)}"
            logger.error("gitlab_connection_test_failed", error=error_msg)
            return False


