import os
import shutil
from pathlib import Path
from typing import Optional, List
from datetime import datetime
from urllib.parse import urlparse, quote

from git import Repo, GitCommandError

from src.config.settings import settings
from src.utils.logging_config import get_logger


logger = get_logger(__name__)


def setup_git_credentials() -> None:
    """
    Setup git credential helper with Azure DevOps credentials.
    
    This function can be called on container startup to ensure credentials
    are configured before any git operations are performed.
    
    Returns:
        None (logs warnings on failure but doesn't raise exceptions)
    """
    # Check if Azure DevOps is configured
    if not settings.azuredevops_url or not settings.azuredevops_username or not settings.azuredevops_password:
        logger.debug(
            "git_credentials_skip_setup",
            reason="Azure DevOps not configured",
            has_url=bool(settings.azuredevops_url),
            has_username=bool(settings.azuredevops_username),
            has_password=bool(settings.azuredevops_password)
        )
        return
    
    try:
        from git import Git
        
        git = Git()
        
        # Configure credential helper to use store mode
        git.config("--global", "credential.helper", "store")
        
        # Create .git-credentials file with Azure DevOps credentials
        credentials_file = Path.home() / ".git-credentials"
        
        # Format: https://username:password@host
        # URL encode username for domain format (DOMAIN\username becomes DOMAIN%5Cusername)
        username = quote(settings.azuredevops_username, safe="")
        password = quote(settings.azuredevops_password, safe="")
        
        # Parse the Azure DevOps URL to get the host
        parsed_url = urlparse(settings.azuredevops_url)
        netloc = parsed_url.netloc
        
        credential_line = f"https://{username}:{password}@{netloc}\n"
        
        # Read existing credentials to avoid duplicates
        existing_creds = []
        if credentials_file.exists():
            with open(credentials_file, 'r') as f:
                existing_creds = f.readlines()
        
        # Check if credential already exists
        if credential_line not in existing_creds:
            # Append new credential
            with open(credentials_file, 'a') as f:
                f.write(credential_line)
            
            # Set secure permissions (read/write for owner only)
            credentials_file.chmod(0o600)
            
            logger.info(
                "git_credentials_configured",
                host=netloc,
                credential_file=str(credentials_file)
            )
        else:
            logger.debug(
                "git_credentials_already_configured",
                host=netloc,
                credential_file=str(credentials_file)
            )
        
    except Exception as e:
        logger.warning(
            "git_credentials_setup_failed",
            error=str(e),
            message="Will fall back to embedded credentials if needed"
        )


class AzureDevOpsRepositoryManager:
    """Manages Azure DevOps repository cloning and local operations."""

    def __init__(self, cache_dir: Optional[str] = None) -> None:
        """
        Initialize repository manager.

        Args:
            cache_dir: Directory for repository cache (defaults to settings)
        """
        self.cache_dir = Path(cache_dir or settings.repo_cache_dir).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info("azuredevops_repository_manager_initialized", cache_dir=str(self.cache_dir))

    def get_repository_path(self, project_name: str, repo_name: str) -> Path:
        """
        Get local path for a repository.

        Args:
            project_name: Azure DevOps project name
            repo_name: Repository name

        Returns:
            Path to local repository directory
        """
        # Create safe directory name from project and repo names
        safe_project = "".join(c for c in project_name if c.isalnum() or c in ("-", "_", "."))
        safe_repo = "".join(c for c in repo_name if c.isalnum() or c in ("-", "_", "."))
        return self.cache_dir / "azuredevops" / safe_project / safe_repo

    def clone_or_update_repository(
        self,
        project_name: str,
        repo_name: str,
        clone_url: str,
        branch: str = "main",
        depth: Optional[int] = None,
        force_fresh: bool = False,
    ) -> Path:
        """
        Clone or update a repository.

        Args:
            project_name: Azure DevOps project name
            repo_name: Repository name
            clone_url: Repository clone URL
            branch: Branch to clone/checkout
            depth: Clone depth (None for full clone)
            force_fresh: Force fresh clone even if repo exists

        Returns:
            Path to local repository directory

        Raises:
            GitCommandError: If git operations fail
        """
        repo_path = self.get_repository_path(project_name, repo_name)

        try:
            if force_fresh and repo_path.exists():
                logger.info("removing_existing_repository", repo_path=str(repo_path))
                shutil.rmtree(repo_path)

            if repo_path.exists() and (repo_path / ".git").exists():
                return self._update_repository(repo_path, branch)
            else:
                return self._clone_repository(clone_url, repo_path, branch, depth)

        except Exception as e:
            error_msg = f"Failed to clone/update repository: {str(e)}"
            logger.error(
                "repository_clone_update_failed",
                project_name=project_name,
                repo_name=repo_name,
                error=error_msg,
            )
            raise

    def _update_repository(self, repo_path: Path, branch: str) -> Path:
        """Update an existing repository."""
        try:
            repo = Repo(str(repo_path))
            
            # Configure git for NTLM authentication if enabled
            if settings.azuredevops_use_ntlm:
                with repo.config_writer() as git_config:
                    git_config.set_value("http", "emulateHTTP", "false")
                    # Get the remote URL to configure http auth scheme
                    remote_url = repo.remotes.origin.url
                    parsed_url = urlparse(remote_url)
                    if parsed_url.scheme == "https":
                        git_config.set_value(
                            f"http \"{parsed_url.scheme}://{parsed_url.netloc}\"",
                            "httpAuthScheme",
                            "ntlm"
                        )
                        if not settings.azuredevops_ssl_verify:
                            git_config.set_value(
                                f"http \"{parsed_url.scheme}://{parsed_url.netloc}\"",
                                "sslVerify",
                                "false"
                            )
            
            # Fetch latest changes
            origin = repo.remotes.origin
            origin.fetch()
            
            # Checkout and reset to the remote branch state
            # This ensures we discard any local changes that might cause conflicts
            if branch not in [head.name for head in repo.heads]:
                # Create local branch tracking remote
                repo.create_head(branch, f"origin/{branch}")
            
            repo.heads[branch].checkout()
            
            # Hard reset to match remote exactly
            repo.git.reset('--hard', f'origin/{branch}')
            
            # Clean any untracked files
            repo.git.clean('-fdx')
            
            logger.info("repository_updated", repo_path=str(repo_path), branch=branch)
            return repo_path
            
        except GitCommandError as e:
            error_msg = f"Failed to update repository: {str(e)}"
            logger.error("repository_update_failed", error=error_msg, repo_path=str(repo_path))
            raise

    def _setup_git_credentials(self) -> None:
        """Setup git credential helper with Azure DevOps credentials."""
        # Use the module-level function for consistency
        setup_git_credentials()

    def _clone_repository(
        self,
        clone_url: str,
        repo_path: Path,
        branch: str,
        depth: Optional[int],
    ) -> Path:
        """Clone a new repository using secure authentication."""
        # Setup git credential helper (only once, checked internally)
        self._setup_git_credentials()
        
        env = os.environ.copy()

        parsed_url = urlparse(clone_url)
        if parsed_url.scheme == "https":
            # Use credential helper - no need to embed credentials in URL
            env["GIT_TERMINAL_PROMPT"] = "0"
            
            # Configure SSL verification
            if not settings.azuredevops_ssl_verify:
                env["GIT_SSL_NO_VERIFY"] = "true"
            
            # Enable verbose output for debugging
            env["GIT_CURL_VERBOSE"] = "1" if settings.debug else "0"
            
            # Encode the path to handle spaces and special characters
            encoded_path = quote(parsed_url.path, safe="/")
            # Use clean URL without embedded credentials - credential helper will provide them
            clean_url = parsed_url._replace(path=encoded_path).geturl()
            authenticated_url = clean_url
        else:
            # Assume SSH - ensure SSH key is configured
            ssh_key_path = os.getenv("AZUREDEVOPS_SSH_KEY_PATH", str(Path.home() / ".ssh" / "id_rsa"))
            env[
                "GIT_SSH_COMMAND"
            ] = f"ssh -i {ssh_key_path} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no"
            authenticated_url = clone_url

        clone_kwargs = {
            "branch": branch,
            "env": env,
        }
        
        # Add git config options
        if parsed_url.scheme == "https":
            config_options = []
            
            # Configure SSL verification
            if not settings.azuredevops_ssl_verify:
                config_options.extend(["-c", f"http.https://{parsed_url.netloc}/.sslVerify=false"])
            
            # Force HTTP/1.1 for Azure DevOps (NTLM/authentication works better with HTTP/1.1)
            if settings.azuredevops_use_ntlm:
                config_options.extend([
                    "-c", "http.version=HTTP/1.1",  # Force HTTP/1.1 protocol
                ])
            
            if config_options:
                clone_kwargs["multi_options"] = config_options
                # Allow unsafe options since we're using -c for legitimate git config
                clone_kwargs["allow_unsafe_options"] = True

        if depth:
            clone_kwargs["depth"] = depth

        try:
            Repo.clone_from(authenticated_url, str(repo_path), **clone_kwargs)
            logger.info(
                "repository_cloned", 
                repo_path=str(repo_path), 
                method="ntlm_credentials" if settings.azuredevops_use_ntlm else "basic_credentials"
            )
            return repo_path
        except GitCommandError as e:  # noqa: BLE001
            error_msg = f"Failed to clone repository: {str(e)}"
            logger.error("repository_clone_failed", error=error_msg, repo_path=str(repo_path))
            if repo_path.exists():
                shutil.rmtree(repo_path)
            raise

    def remove_repository(self, project_name: str, repo_name: str) -> bool:
        """
        Remove a repository from local cache.

        Args:
            project_name: Azure DevOps project name
            repo_name: Repository name

        Returns:
            True if removed successfully, False if not found
        """
        repo_path = self.get_repository_path(project_name, repo_name)
        
        if repo_path.exists():
            try:
                shutil.rmtree(repo_path)
                logger.info("repository_removed", repo_path=str(repo_path))
                return True
            except Exception as e:
                error_msg = f"Failed to remove repository: {str(e)}"
                logger.error("repository_removal_failed", error=error_msg, repo_path=str(repo_path))
                raise
        else:
            logger.warning("repository_not_found_for_removal", repo_path=str(repo_path))
            return False

    def get_repository_size(self, project_name: str, repo_name: str) -> int:
        """
        Get repository size in bytes.

        Args:
            project_name: Azure DevOps project name
            repo_name: Repository name

        Returns:
            Size in bytes, 0 if repository doesn't exist
        """
        repo_path = self.get_repository_path(project_name, repo_name)
        
        if not repo_path.exists():
            return 0
            
        try:
            total_size = 0
            for dirpath, dirnames, filenames in os.walk(repo_path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    if os.path.exists(filepath):
                        total_size += os.path.getsize(filepath)
            return total_size
        except Exception as e:
            logger.warning("repository_size_calculation_failed", error=str(e), repo_path=str(repo_path))
            return 0

    def cleanup_old_repositories(self, max_age_days: int = 7) -> int:
        """
        Clean up old repositories based on age.

        Args:
            max_age_days: Maximum age in days before cleanup

        Returns:
            Number of repositories cleaned up
        """
        import time
        from datetime import datetime, timedelta

        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
        cleaned_count = 0
        
        azuredevops_cache = self.cache_dir / "azuredevops"
        if not azuredevops_cache.exists():
            return 0

        try:
            for project_dir in azuredevops_cache.iterdir():
                if not project_dir.is_dir():
                    continue
                    
                for repo_dir in project_dir.iterdir():
                    if not repo_dir.is_dir():
                        continue
                        
                    # Check last modification time
                    if repo_dir.stat().st_mtime < cutoff_time:
                        try:
                            shutil.rmtree(repo_dir)
                            cleaned_count += 1
                            logger.info("old_repository_cleaned", repo_path=str(repo_dir))
                        except Exception as e:
                            logger.warning("repository_cleanup_failed", error=str(e), repo_path=str(repo_dir))
                            
                # Remove empty project directories
                try:
                    if not any(project_dir.iterdir()):
                        project_dir.rmdir()
                        logger.info("empty_project_directory_removed", project_path=str(project_dir))
                except Exception:
                    pass  # Ignore errors when removing empty directories
                    
        except Exception as e:
            logger.error("repository_cleanup_error", error=str(e))
            
        logger.info("repository_cleanup_completed", cleaned_count=cleaned_count)
        return cleaned_count

    def list_cached_repositories(self) -> list[dict]:
        """
        List all cached repositories.

        Returns:
            List of repository information dictionaries
        """
        repositories = []
        azuredevops_cache = self.cache_dir / "azuredevops"
        
        if not azuredevops_cache.exists():
            return repositories

        try:
            for project_dir in azuredevops_cache.iterdir():
                if not project_dir.is_dir():
                    continue
                    
                project_name = project_dir.name
                for repo_dir in project_dir.iterdir():
                    if not repo_dir.is_dir() or not (repo_dir / ".git").exists():
                        continue
                        
                    repo_name = repo_dir.name
                    size = self.get_repository_size(project_name, repo_name)
                    
                    repositories.append({
                        "project_name": project_name,
                        "repo_name": repo_name,
                        "path": str(repo_dir),
                        "size_bytes": size,
                        "last_modified": repo_dir.stat().st_mtime,
                    })
                    
        except Exception as e:
            logger.error("list_cached_repositories_failed", error=str(e))
            
        return repositories

    def get_file_tree(self, repo_path: Path, extensions: Optional[list[str]] = None) -> list[Path]:
        """
        Get list of relevant files in repository.

        Args:
            repo_path: Path to local repository
            extensions: File extensions to include (defaults to common code files)

        Returns:
            List of file paths to process
        """
        if extensions is None:
            extensions = [
                # Code files
                ".py", ".js", ".ts", ".tsx", ".jsx", ".vue", ".cs", ".java", 
                ".go", ".rs", ".cpp", ".c", ".h", ".hpp", ".php", ".rb", 
                ".swift", ".kt", ".scala", ".clj", ".fs", ".vb",
                # Dependency and config files
                ".csproj", ".sln",  # NuGet dependencies
                ".json", ".yaml", ".yml", ".xml", ".toml", ".ini", ".cfg",
                # Database files
                ".sql",
                # Documentation
                ".md", ".markdown"
            ]

        files = []
        try:
            for ext in extensions:
                files.extend(repo_path.rglob(f"*{ext}"))
            
            # Filter out common directories to ignore
            ignored_dirs = {
                ".git", ".svn", ".hg", "node_modules", "__pycache__", 
                ".pytest_cache", "venv", ".venv", "env", ".env",
                "dist", "build", "target", "bin", "obj", ".vs", 
                ".vscode", ".idea", "coverage", ".coverage",
                "vendor", "packages", ".nuget"
            }
            
            filtered_files = []
            for file_path in files:
                # Check if any parent directory is in ignored list
                if not any(part in ignored_dirs for part in file_path.parts):
                    filtered_files.append(file_path)
            
            logger.info(
                "file_tree_generated",
                repo_path=str(repo_path),
                total_files=len(filtered_files),
                extensions=extensions
            )
            
            return sorted(filtered_files)
            
        except Exception as e:
            error_msg = f"Failed to get file tree: {str(e)}"
            logger.error("file_tree_generation_failed", error=error_msg, repo_path=str(repo_path))
            raise

    def get_head_commit(self, repo_path: Path) -> dict:
        """
        Get information about the HEAD commit.

        Args:
            repo_path: Path to local repository

        Returns:
            Dictionary with commit information
        """
        try:
            repo = Repo(str(repo_path))
            commit = repo.head.commit
            
            return {
                "sha": commit.hexsha,
                "message": str(commit.message).strip(),
                "author_name": commit.author.name,
                "author_email": commit.author.email,
                "committed_date": datetime.fromtimestamp(commit.committed_date),
                "parent_sha": commit.parents[0].hexsha if commit.parents else None
            }
        except Exception as e:
            logger.error("failed_to_get_head_commit", repo_path=str(repo_path), error=str(e))
            return None
