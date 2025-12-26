import os
import shutil
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from urllib.parse import quote, urlparse

from git import Repo, GitCommandError

from src.config.settings import settings
from src.config.enums import LanguageEnum
from src.utils.logging_config import get_logger
from src.utils.metrics import repository_sync_duration, repository_sync_total


logger = get_logger(__name__)


class RepositoryManager:
    """Manages repository cloning, caching, and file discovery."""

    def __init__(self, cache_dir: Optional[str] = None) -> None:
        """
        Initialize repository manager.

        Args:
            cache_dir: Directory for caching repositories
        """
        self.cache_dir = Path(cache_dir or settings.repo_cache_dir).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info("repository_manager_initialized", cache_dir=str(self.cache_dir))

    def clone_or_update(
        self,
        repo_url: str,
        repo_name: str,
        branch: str = "main",
        depth: Optional[int] = 1,
    ) -> Path:
        """
        Clone repository or update if already exists.

        Args:
            repo_url: Repository URL
            repo_name: Repository name (used for cache directory)
            branch: Branch to clone/checkout
            depth: Clone depth (None for full clone)

        Returns:
            Path to repository directory
        """
        repo_path = self.cache_dir / repo_name.replace("/", "_")

        with repository_sync_duration.labels(repository_name=repo_name).time():
            try:
                if repo_path.exists():
                    logger.info("repository_updating", repo_name=repo_name, path=str(repo_path))
                    repo_path = self._update_repository(repo_path, branch)
                else:
                    logger.info("repository_cloning", repo_name=repo_name, path=str(repo_path))
                    repo_path = self._clone_repository(repo_url, repo_path, branch, depth)

                repository_sync_total.labels(status="success").inc()
                logger.info("repository_sync_successful", repo_name=repo_name)
                return repo_path

            except Exception as e:  # noqa: BLE001
                repository_sync_total.labels(status="failure").inc()
                error_msg = f"Failed to sync repository: {str(e)}"
                logger.error(
                    "repository_sync_failed",
                    repo_name=repo_name,
                    error=error_msg,
                )
                raise

    def _clone_repository(
        self,
        repo_url: str,
        repo_path: Path,
        branch: str,
        depth: Optional[int],
    ) -> Path:
        """Clone a new repository using secure authentication."""
        # Use Git credential helper to avoid exposing tokens in URLs/logs
        env = os.environ.copy()

        parsed_url = urlparse(repo_url)
        if parsed_url.scheme == "https":
            # Embed OAuth token in clone URL to ensure non-interactive authentication
            env["GIT_TERMINAL_PROMPT"] = "0"
            safe_token = quote(settings.gitlab_token, safe="")
            token_netloc = f"oauth2:{safe_token}@{parsed_url.netloc}"
            authenticated_url = parsed_url._replace(netloc=token_netloc).geturl()
        else:
            # Assume SSH - ensure SSH key is configured
            ssh_key_path = os.getenv("GITLAB_SSH_KEY_PATH", str(Path.home() / ".ssh" / "id_rsa"))
            env[
                "GIT_SSH_COMMAND"
            ] = f"ssh -i {ssh_key_path} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no"
            authenticated_url = repo_url

        clone_kwargs = {
            "branch": branch,
            "env": env,
        }

        if depth:
            clone_kwargs["depth"] = depth

        try:
            Repo.clone_from(authenticated_url, str(repo_path), **clone_kwargs)
            logger.info("repository_cloned", repo_path=str(repo_path), method="secure_credentials")
            return repo_path
        except GitCommandError as e:  # noqa: BLE001
            error_msg = f"Failed to clone repository: {str(e)}"
            logger.error("repository_clone_failed", error=error_msg, repo_path=str(repo_path))
            if repo_path.exists():
                shutil.rmtree(repo_path)
            raise

    def _update_repository(self, repo_path: Path, branch: str) -> Path:
        """Update existing repository."""
        try:
            repo = Repo(repo_path)
            origin = repo.remotes.origin

            # Fetch all branches from remote
            # Use repo.git.fetch to fetch all branches from origin
            repo.git.fetch("origin")

            remote_branch_ref = f"origin/{branch}"
            
            # Check if branch exists remotely
            remote_branch_exists = any(
                ref.name == remote_branch_ref 
                for ref in origin.refs
            )
            
            # If branch doesn't exist, get default branch from origin/HEAD
            if not remote_branch_exists:
                default_branch_name = None
                try:
                    # Get default branch from origin/HEAD using git command
                    # origin/HEAD is a symbolic ref pointing to the default branch
                    head_output = repo.git.symbolic_ref("refs/remotes/origin/HEAD", "--short")
                    # Output is like "origin/main" or "origin/master"
                    default_branch_name = head_output.replace("origin/", "")
                    logger.warning(
                        "branch_not_found_using_default",
                        requested_branch=branch,
                        default_branch=default_branch_name
                    )
                except GitCommandError:
                    # If origin/HEAD doesn't exist or can't be accessed, try common default branch names
                    common_defaults = ["main", "master", "develop"]
                    for default_name in common_defaults:
                        default_ref = f"origin/{default_name}"
                        if any(ref.name == default_ref for ref in origin.refs):
                            default_branch_name = default_name
                            logger.warning(
                                "branch_not_found_using_common_default",
                                requested_branch=branch,
                                default_branch=default_name
                            )
                            break
                
                if default_branch_name:
                    branch = default_branch_name
                    remote_branch_ref = f"origin/{branch}"
                else:
                    # No default branch found - list available branches
                    remote_branches = [
                        ref.name.replace("origin/", "") 
                        for ref in origin.refs 
                        if ref.name.startswith("origin/") 
                        and not ref.name.endswith("/HEAD")
                        and "/" not in ref.name.replace("origin/", "")  # Exclude nested refs
                    ]
                    error_msg = (
                        f"Branch '{branch}' does not exist in remote repository. "
                        f"Available branches: {', '.join(remote_branches) if remote_branches else 'none'}"
                    )
                    logger.error(
                        "branch_not_found",
                        branch=branch,
                        available_branches=remote_branches,
                        error=error_msg
                    )
                    raise GitCommandError(
                        ["git", "checkout", branch],
                        1,
                        error_msg.encode(),
                        b""
                    )
            
            # Check if branch exists locally
            local_branches = [ref.name for ref in repo.branches]
            
            try:
                if branch in local_branches:
                    # Branch exists locally - checkout and reset
                    repo.git.checkout(branch)
                    repo.git.reset("--hard", remote_branch_ref)
                else:
                    # Branch doesn't exist locally - try to checkout from remote
                    # This will create a tracking branch if the remote branch exists
                    repo.git.checkout("-b", branch, remote_branch_ref)
                    repo.git.reset("--hard", remote_branch_ref)
            except GitCommandError as checkout_error:  # noqa: BLE001
                # Branch exists remotely but checkout failed for another reason
                error_msg = f"Failed to checkout branch '{branch}': {str(checkout_error)}"
                logger.error("branch_checkout_failed", branch=branch, error=error_msg)
                raise

            return repo_path
        except GitCommandError as e:  # noqa: BLE001
            error_msg = f"Failed to update repository: {str(e)}"
            logger.error("repository_update_failed", error=error_msg)
            raise

    def get_file_tree(self, repo_path: Path, extensions: Optional[List[str]] = None) -> List[Path]:
        """
        Get list of relevant files in repository.

        Args:
            repo_path: Path to repository
            extensions: File extensions to include (e.g., [".cs", ".js"])

        Returns:
            List of file paths
        """
        if extensions is None:
            extensions = [
                # Code files
                ".cs", ".js", ".ts", ".vue", ".tsx", ".jsx",
                # Dependency files
                ".csproj", ".sln", ".json",  # .csproj for NuGet, package.json for npm
                # Configuration files
                ".md", ".markdown", ".sql", ".ddl"
            ]

        # Directories to exclude
        exclude_dirs = {
            "node_modules",
            "bin",
            "obj",
            ".git",
            "dist",
            "build",
            ".next",
            "__pycache__",
            "venv",
            "vendor",
            "packages",
            ".nuxt",
            ".cache",
            "coverage",
            "test_results",
        }

        files: List[Path] = []
        total_size = 0

        for file_path in repo_path.rglob("*"):
            if not file_path.is_file():
                continue

            # Skip excluded directories
            if any(exc in file_path.parts for exc in exclude_dirs):
                continue

            # Filter by extension
            if file_path.suffix.lower() not in extensions:
                continue

            # Check file size
            file_size = file_path.stat().st_size
            if file_size > settings.parse_max_file_size_mb * 1024 * 1024:
                logger.warning(
                    "file_too_large_skipped",
                    file_path=str(file_path),
                    size_mb=file_size / (1024 * 1024),
                )
                continue

            total_size += file_size
            files.append(file_path)

        logger.info(
            "file_tree_discovered",
            repo_path=str(repo_path),
            file_count=len(files),
            total_size_mb=total_size / (1024 * 1024),
        )

        return files

    def detect_language(self, file_path: Path) -> LanguageEnum:
        """
        Detect programming language from file extension.

        Args:
            file_path: Path to file

        Returns:
            Detected language enum
        """
        extension_map = {
            ".cs": LanguageEnum.CSHARP,
            ".js": LanguageEnum.JAVASCRIPT,
            ".jsx": LanguageEnum.JAVASCRIPT,
            ".ts": LanguageEnum.TYPESCRIPT,
            ".tsx": LanguageEnum.TYPESCRIPT,
            ".vue": LanguageEnum.VUE,
            ".py": LanguageEnum.PYTHON,
            ".go": LanguageEnum.GO,
            ".java": LanguageEnum.JAVA,
            ".sql": LanguageEnum.SQL,
            ".ddl": LanguageEnum.SQL,
            ".md": LanguageEnum.MARKDOWN,
            ".markdown": LanguageEnum.MARKDOWN,
            ".csproj": LanguageEnum.CSHARP,  # .csproj files are C# project files
            ".sln": LanguageEnum.CSHARP,     # .sln files are C# solution files
            ".json": LanguageEnum.JAVASCRIPT,  # .json files (package.json, etc.) are JavaScript ecosystem
        }

        suffix = file_path.suffix.lower()
        
        # Special handling for specific JSON files
        if suffix == ".json":
            filename = file_path.name.lower()
            # Categorize based on filename
            if filename.startswith("appsettings"):
                return LanguageEnum.CSHARP  # appsettings.json is C# config
            elif filename == "package.json":
                return LanguageEnum.JAVASCRIPT  # package.json is npm/JavaScript
            # Default to JavaScript for other JSON files
            return LanguageEnum.JAVASCRIPT
        
        return extension_map.get(suffix, LanguageEnum.UNKNOWN)

    def cleanup_repository(self, repo_name: str) -> None:
        """
        Remove repository from cache.

        Args:
            repo_name: Repository name
        """
        repo_path = self.cache_dir / repo_name.replace("/", "_")

        if repo_path.exists():
            try:
                shutil.rmtree(repo_path)
                logger.info("repository_cleaned_up", repo_name=repo_name)
            except Exception as e:  # noqa: BLE001
                error_msg = f"Failed to cleanup repository: {str(e)}"
                logger.error(
                    "repository_cleanup_failed",
                    repo_name=repo_name,
                    error=error_msg,
                )
                raise

    def get_repository_size(self, repo_path: Path) -> int:
        """
        Get total size of repository in bytes.

        Args:
            repo_path: Path to repository

        Returns:
            Size in bytes
        """
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(repo_path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                if os.path.isfile(filepath):
                    total_size += os.path.getsize(filepath)

        return total_size

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


