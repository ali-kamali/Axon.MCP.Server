"""GitHub repository manager for cloning and local file operations."""

import os
import shutil
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from urllib.parse import quote, urlparse

from git import Repo, GitCommandError

from src.config.settings import get_settings
from src.config.enums import LanguageEnum
from src.utils.logging_config import get_logger
from src.utils.metrics import repository_sync_duration, repository_sync_total


logger = get_logger(__name__)


class GitHubRepositoryManager:
    """Manages GitHub repository cloning, caching, and file discovery.

    Cache path uses the same pattern as GitLab:
        cache_dir / path_with_namespace.replace("/", "_")
    Since GitHub's owner/repo maps cleanly to owner_repo on disk.
    """

    def __init__(self, cache_dir: Optional[str] = None) -> None:
        self.cache_dir = Path(cache_dir or get_settings().repo_cache_dir).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info("github_repository_manager_initialized", cache_dir=str(self.cache_dir))

    def clone_or_update(
        self,
        repo_url: str,
        repo_name: str,
        branch: str = "main",
        depth: Optional[int] = 1,
    ) -> Path:
        """Clone repository or update if already exists.

        Args:
            repo_url: Repository URL (html_url)
            repo_name: path_with_namespace (owner/repo)
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

            except Exception as e:
                repository_sync_total.labels(status="failure").inc()
                logger.error("repository_sync_failed", repo_name=repo_name, error=str(e))
                raise

    def _clone_repository(
        self,
        repo_url: str,
        repo_path: Path,
        branch: str,
        depth: Optional[int],
    ) -> Path:
        """Clone a new repository using token authentication."""
        env = os.environ.copy()

        parsed_url = urlparse(repo_url)
        if parsed_url.scheme == "https":
            env["GIT_TERMINAL_PROMPT"] = "0"
            token = get_settings().github_token
            if token:
                safe_token = quote(token, safe="")
                token_netloc = f"x-access-token:{safe_token}@{parsed_url.netloc}"
                authenticated_url = parsed_url._replace(netloc=token_netloc).geturl()
            else:
                authenticated_url = repo_url
        else:
            ssh_key_path = os.getenv("GITHUB_SSH_KEY_PATH", str(Path.home() / ".ssh" / "id_rsa"))
            env["GIT_SSH_COMMAND"] = (
                f"ssh -i {ssh_key_path} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no"
            )
            authenticated_url = repo_url

        # Ensure clone URL ends with .git
        if not authenticated_url.endswith(".git"):
            authenticated_url += ".git"

        clone_kwargs = {
            "branch": branch,
            "env": env,
        }
        if depth:
            clone_kwargs["depth"] = depth

        try:
            Repo.clone_from(authenticated_url, str(repo_path), **clone_kwargs)
            logger.info("repository_cloned", repo_path=str(repo_path), method="github_token")
            return repo_path
        except GitCommandError as e:
            logger.error("repository_clone_failed", error=str(e), repo_path=str(repo_path))
            if repo_path.exists():
                shutil.rmtree(repo_path)
            raise

    def _update_repository(self, repo_path: Path, branch: str) -> Path:
        """Update existing repository."""
        try:
            repo = Repo(repo_path)
            origin = repo.remotes.origin

            repo.git.fetch("origin")

            remote_branch_ref = f"origin/{branch}"

            remote_branch_exists = any(
                ref.name == remote_branch_ref
                for ref in origin.refs
            )

            if not remote_branch_exists:
                default_branch_name = None
                try:
                    head_output = repo.git.symbolic_ref("refs/remotes/origin/HEAD", "--short")
                    default_branch_name = head_output.replace("origin/", "")
                    logger.warning(
                        "branch_not_found_using_default",
                        requested_branch=branch,
                        default_branch=default_branch_name,
                    )
                except GitCommandError:
                    common_defaults = ["main", "master", "develop"]
                    for default_name in common_defaults:
                        default_ref = f"origin/{default_name}"
                        if any(ref.name == default_ref for ref in origin.refs):
                            default_branch_name = default_name
                            logger.warning(
                                "branch_not_found_using_common_default",
                                requested_branch=branch,
                                default_branch=default_name,
                            )
                            break

                if default_branch_name:
                    branch = default_branch_name
                    remote_branch_ref = f"origin/{branch}"
                else:
                    remote_branches = [
                        ref.name.replace("origin/", "")
                        for ref in origin.refs
                        if ref.name.startswith("origin/")
                        and not ref.name.endswith("/HEAD")
                        and "/" not in ref.name.replace("origin/", "")
                    ]
                    raise GitCommandError(
                        ["git", "checkout", branch],
                        1,
                        f"Branch '{branch}' not found. Available: {', '.join(remote_branches)}".encode(),
                        b"",
                    )

            local_branches = [ref.name for ref in repo.branches]

            if branch in local_branches:
                repo.git.checkout(branch)
                repo.git.reset("--hard", remote_branch_ref)
            else:
                repo.git.checkout("-b", branch, remote_branch_ref)
                repo.git.reset("--hard", remote_branch_ref)

            return repo_path
        except GitCommandError as e:
            logger.error("repository_update_failed", error=str(e))
            raise

    def get_file_tree(self, repo_path: Path, extensions: Optional[List[str]] = None) -> List[Path]:
        """Get list of relevant files in repository.

        Uses the same extensions and exclusion dirs as the GitLab RepositoryManager.
        """
        if extensions is None:
            extensions = [
                ".cs", ".js", ".ts", ".vue", ".tsx", ".jsx",
                ".csproj", ".sln", ".json",
                ".md", ".markdown", ".sql", ".ddl",
            ]

        exclude_dirs = {
            "node_modules", "bin", "obj", ".git", "dist", "build",
            ".next", "__pycache__", "venv", "vendor", "packages",
            ".nuxt", ".cache", "coverage", "test_results",
        }

        files: List[Path] = []
        total_size = 0

        for file_path in repo_path.rglob("*"):
            if not file_path.is_file():
                continue
            if any(exc in file_path.parts for exc in exclude_dirs):
                continue
            if file_path.suffix.lower() not in extensions:
                continue

            file_size = file_path.stat().st_size
            if file_size > get_settings().parse_max_file_size_mb * 1024 * 1024:
                logger.warning("file_too_large_skipped", file_path=str(file_path), size_mb=file_size / (1024 * 1024))
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
        """Detect programming language from file extension."""
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
            ".csproj": LanguageEnum.CSHARP,
            ".sln": LanguageEnum.CSHARP,
            ".json": LanguageEnum.JAVASCRIPT,
        }

        suffix = file_path.suffix.lower()

        if suffix == ".json":
            filename = file_path.name.lower()
            if filename.startswith("appsettings"):
                return LanguageEnum.CSHARP
            elif filename == "package.json":
                return LanguageEnum.JAVASCRIPT
            return LanguageEnum.JAVASCRIPT

        return extension_map.get(suffix, LanguageEnum.UNKNOWN)

    def cleanup_repository(self, repo_name: str) -> None:
        """Remove repository from cache."""
        repo_path = self.cache_dir / repo_name.replace("/", "_")
        if repo_path.exists():
            try:
                shutil.rmtree(repo_path)
                logger.info("repository_cleaned_up", repo_name=repo_name)
            except Exception as e:
                logger.error("repository_cleanup_failed", repo_name=repo_name, error=str(e))
                raise

    def get_repository_size(self, repo_path: Path) -> int:
        """Get total size of repository in bytes."""
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(repo_path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                if os.path.isfile(filepath):
                    total_size += os.path.getsize(filepath)
        return total_size

    def get_head_commit(self, repo_path: Path) -> dict:
        """Get information about the HEAD commit."""
        try:
            repo = Repo(str(repo_path))
            commit = repo.head.commit
            return {
                "sha": commit.hexsha,
                "message": str(commit.message).strip(),
                "author_name": commit.author.name,
                "author_email": commit.author.email,
                "committed_date": datetime.fromtimestamp(commit.committed_date),
                "parent_sha": commit.parents[0].hexsha if commit.parents else None,
            }
        except Exception as e:
            logger.error("failed_to_get_head_commit", repo_path=str(repo_path), error=str(e))
            return None
