import requests
from typing import List, Dict, Optional
from urllib.parse import urljoin
from requests_ntlm import HttpNtlmAuth

from src.config.settings import settings
from src.utils.logging_config import get_logger


logger = get_logger(__name__)


class AzureDevOpsClient:
    """Azure DevOps API client wrapper with authentication and error handling."""

    def __init__(self, username: Optional[str] = None, password: Optional[str] = None, url: Optional[str] = None) -> None:
        """
        Initialize Azure DevOps client.

        Args:
            username: Azure DevOps username (defaults to settings)
            password: Azure DevOps password (defaults to settings)
            url: Azure DevOps URL (defaults to settings)
        """
        self.url = url or settings.azuredevops_url
        self.username = username or settings.azuredevops_username
        self.password = password or settings.azuredevops_password
        
        # Use NTLM authentication
        self.auth = HttpNtlmAuth(self.username, self.password)
        
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Test connection during initialization
        try:
            self._test_connection()
            logger.info("azuredevops_client_initialized", url=self.url)
        except Exception as e:
            error_msg = f"Failed to authenticate with Azure DevOps: {str(e)}"
            logger.error("azuredevops_authentication_failed", error=error_msg)
            raise

    def _test_connection(self) -> None:
        """Test Azure DevOps connection and authentication."""
        try:
            # Test with a simple API call to get projects
            url = urljoin(self.url, "_apis/projects?api-version=6.0")
            response = requests.get(url, headers=self.headers, auth=self.auth, timeout=30)
            response.raise_for_status()
            logger.info("azuredevops_connection_test_successful")
        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to test Azure DevOps connection: {str(e)}"
            logger.error("azuredevops_connection_test_failed", error=error_msg)
            raise

    def _determine_default_branch(self, project_name: str, repo_name: str) -> str:
        """
        Determine the default branch to use based on priority rules.
        
        Priority:
        1. "prd" branch if it exists
        2. "production" branch if it exists
        3. Repository's default branch
        
        Args:
            project_name: Azure DevOps project name
            repo_name: Repository name
            
        Returns:
            Branch name to use
        """
        try:
            # Get list of branches
            url = urljoin(self.url, f"{project_name}/_apis/git/repositories/{repo_name}/refs?filter=heads/&api-version=6.0")
            response = requests.get(url, headers=self.headers, auth=self.auth, timeout=30)
            response.raise_for_status()
            
            refs_data = response.json()
            branch_names = {ref["name"].replace("refs/heads/", "") for ref in refs_data.get("value", [])}
            
            # Check priority order
            if "prd" in branch_names:
                logger.info(
                    "branch_priority_selected",
                    project=project_name,
                    repo=repo_name,
                    selected_branch="prd",
                    reason="prd_branch_exists"
                )
                return "prd"
            elif "production" in branch_names:
                logger.info(
                    "branch_priority_selected",
                    project=project_name,
                    repo=repo_name,
                    selected_branch="production",
                    reason="production_branch_exists"
                )
                return "production"
            else:
                # Get repository default branch
                repo_url = urljoin(self.url, f"{project_name}/_apis/git/repositories/{repo_name}?api-version=6.0")
                repo_response = requests.get(repo_url, headers=self.headers, auth=self.auth, timeout=30)
                repo_response.raise_for_status()
                repo_data = repo_response.json()
                default = repo_data.get("defaultBranch", "refs/heads/main").replace("refs/heads/", "")
                
                logger.info(
                    "branch_priority_selected",
                    project=project_name,
                    repo=repo_name,
                    selected_branch=default,
                    reason="using_repo_default"
                )
                return default
        except Exception as e:
            # If we can't get branches, fallback to main
            error_msg = f"Failed to list branches, using default: {str(e)}"
            logger.warning(
                "branch_list_failed_fallback",
                project=project_name,
                repo=repo_name,
                error=error_msg
            )
            return "main"

    def get_project(self, project_name: str) -> Dict:
        """
        Get project details by name.

        Args:
            project_name: Azure DevOps project name

        Returns:
            Project metadata dictionary
        """
        try:
            url = urljoin(self.url, f"_apis/projects/{project_name}?api-version=6.0")
            response = requests.get(url, headers=self.headers, auth=self.auth, timeout=30)
            response.raise_for_status()
            
            project_data = response.json()
            
            return {
                "id": project_data["id"],
                "name": project_data["name"],
                "description": project_data.get("description", ""),
                "url": project_data.get("url", ""),
                "state": project_data.get("state", ""),
                "visibility": project_data.get("visibility", "private"),
                "last_update_time": project_data.get("lastUpdateTime", ""),
            }
        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to get Azure DevOps project: {str(e)}"
            logger.error("azuredevops_project_get_failed", project_name=project_name, error=error_msg)
            raise

    def list_project_repositories(self, project_name: str) -> List[Dict]:
        """
        List all repositories in an Azure DevOps project.

        Args:
            project_name: Azure DevOps project name

        Returns:
            List of repository metadata dictionaries
        """
        try:
            url = urljoin(self.url, f"{project_name}/_apis/git/repositories?api-version=6.0")
            response = requests.get(url, headers=self.headers, auth=self.auth, timeout=30)
            response.raise_for_status()
            
            repos_data = response.json()
            repositories = repos_data.get("value", [])

            result = []
            for repo in repositories:
                if repo.get("isDisabled", False):
                    continue
                
                # Get default branch efficiently
                default_branch = repo.get("defaultBranch", "refs/heads/main").replace("refs/heads/", "")
                
                # Generate path_with_namespace in format: project_name/repo_name
                path_with_namespace = f"{project_name}/{repo['name']}"
                
                result.append({
                    "id": repo["id"],
                    "name": repo["name"],
                    "project_name": project_name,
                    "path_with_namespace": path_with_namespace,
                    "url": repo["webUrl"],
                    "clone_url": repo["remoteUrl"],
                    "default_branch": default_branch,
                    "size": repo.get("size", 0),
                    "is_fork": repo.get("isFork", False),
                    "is_disabled": repo.get("isDisabled", False),
                })
            
            return result
        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to list Azure DevOps project repositories: {str(e)}"
            logger.error("azuredevops_repos_list_failed", project_name=project_name, error=error_msg)
            raise

    def get_repository(self, project_name: str, repo_name: str) -> Dict:
        """
        Get repository details.

        Args:
            project_name: Azure DevOps project name
            repo_name: Repository name

        Returns:
            Repository metadata dictionary
        """
        try:
            url = urljoin(self.url, f"{project_name}/_apis/git/repositories/{repo_name}?api-version=6.0")
            response = requests.get(url, headers=self.headers, auth=self.auth, timeout=30)
            response.raise_for_status()
            
            repo_data = response.json()
            default_branch = self._determine_default_branch(project_name, repo_name)
            
            return {
                "id": repo_data["id"],
                "name": repo_data["name"],
                "project_name": project_name,
                "project_id": repo_data["project"]["id"],
                "url": repo_data["webUrl"],
                "clone_url": repo_data["remoteUrl"],
                "default_branch": default_branch,
                "size": repo_data.get("size", 0),
                "is_fork": repo_data.get("isFork", False),
                "is_disabled": repo_data.get("isDisabled", False),
            }
        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to get Azure DevOps repository: {str(e)}"
            logger.error("azuredevops_repo_get_failed", project_name=project_name, repo_name=repo_name, error=error_msg)
            raise

    def get_latest_commit(self, project_name: str, repo_name: str, branch: str | None = None) -> Dict:
        """
        Get latest commit for a branch.

        Args:
            project_name: Azure DevOps project name
            repo_name: Repository name
            branch: Branch name (defaults to default_branch)

        Returns:
            Commit metadata dictionary
        """
        try:
            if not branch:
                repo_info = self.get_repository(project_name, repo_name)
                branch = repo_info["default_branch"]
            
            url = urljoin(self.url, f"{project_name}/_apis/git/repositories/{repo_name}/commits?searchCriteria.itemVersion.version={branch}&$top=1&api-version=6.0")
            response = requests.get(url, headers=self.headers, auth=self.auth, timeout=30)
            response.raise_for_status()
            
            commits_data = response.json()
            commits = commits_data.get("value", [])

            if not commits:
                return {}

            commit = commits[0]
            return {
                "sha": commit["commitId"],
                "message": commit["comment"],
                "author_name": commit["author"]["name"],
                "author_email": commit["author"]["email"],
                "committed_date": commit["author"]["date"],
                "title": commit["comment"].split('\n')[0] if commit["comment"] else "",
            }
        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to get Azure DevOps commit: {str(e)}"
            logger.error(
                "azuredevops_commit_get_failed",
                project_name=project_name,
                repo_name=repo_name,
                branch=branch,
                error=error_msg,
            )
            raise

    def list_repository_files(
        self,
        project_name: str,
        repo_name: str,
        path: str = "",
        branch: str | None = None,
        recursive: bool = True,
    ) -> List[Dict]:
        """
        List files in a repository.

        Args:
            project_name: Azure DevOps project name
            repo_name: Repository name
            path: Directory path to list
            branch: Git branch
            recursive: Whether to list recursively

        Returns:
            List of file metadata dictionaries
        """
        try:
            if not branch:
                repo_info = self.get_repository(project_name, repo_name)
                branch = repo_info["default_branch"]

            url = urljoin(self.url, f"{project_name}/_apis/git/repositories/{repo_name}/items")
            params = {
                "scopePath": path,
                "recursionLevel": "Full" if recursive else "OneLevel",
                "versionDescriptor.version": branch,
                "versionDescriptor.versionType": "branch",
                "api-version": "6.0"
            }
            
            response = requests.get(url, headers=self.headers, auth=self.auth, params=params, timeout=30)
            response.raise_for_status()
            
            items_data = response.json()
            items = items_data.get("value", [])

            return [
                {
                    "path": item["path"],
                    "name": item["path"].split("/")[-1],
                    "type": "file" if not item["isFolder"] else "folder",
                    "size": item.get("size", 0),
                }
                for item in items
                if not item["isFolder"]  # Only return files, not folders
            ]
        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to list Azure DevOps repository files: {str(e)}"
            logger.error(
                "azuredevops_files_list_failed",
                project_name=project_name,
                repo_name=repo_name,
                path=path,
                error=error_msg,
            )
            raise

    def get_optimal_branch_for_repository(self, project_name: str, repo_name: str) -> str:
        """
        Get the optimal branch for a repository using priority rules.
        
        Args:
            project_name: Azure DevOps project name
            repo_name: Repository name
            
        Returns:
            Branch name to use
        """
        try:
            return self._determine_default_branch(project_name, repo_name)
        except Exception as e:
            error_msg = f"Failed to determine optimal branch: {str(e)}"
            logger.error(
                "optimal_branch_determination_failed",
                project_name=project_name,
                repo_name=repo_name,
                error=error_msg
            )
            # Fallback to main
            return "main"

    def test_connection(self) -> bool:
        """
        Test Azure DevOps connection and authentication.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            self._test_connection()
            logger.info("azuredevops_connection_test_successful")
            return True
        except Exception as e:
            error_msg = f"Failed to test Azure DevOps connection: {str(e)}"
            logger.error("azuredevops_connection_test_failed", error=error_msg)
            return False
