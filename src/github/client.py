"""GitHub API client with rate-limit aware exponential backoff."""

import time
import math
from typing import List, Dict, Optional, Any

import requests

from src.config.settings import get_settings
from src.utils.logging_config import get_logger


logger = get_logger(__name__)


class GitHubClient:
    """GitHub REST API client with automatic rate-limit backoff.

    Rate limiting strategy:
    - Reads X-RateLimit-Remaining and X-RateLimit-Reset on every response
    - Warns when remaining < 100
    - On 403/429 (rate limited): waits until reset + 5s buffer
    - If reset header missing: exponential backoff min(60 * 2^attempt, 960)s
    - Max 5 retries per request — never skips data
    """

    MAX_RETRIES = 5

    def __init__(self, token: Optional[str] = None, url: Optional[str] = None) -> None:
        self.url = (url or get_settings().github_url).rstrip("/")
        self.token = token or get_settings().github_token
        self.session = requests.Session()
        if self.token:
            self.session.headers.update({
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3+json",
            })
        else:
            self.session.headers.update({
                "Accept": "application/vnd.github.v3+json",
            })
        logger.info("github_client_initialized", url=self.url, authenticated=bool(self.token))

    def _request(self, method: str, endpoint: str, **kwargs: Any) -> requests.Response:
        """Central request method with rate-limit handling and retries.

        ALL API calls go through this method to ensure rate limits are
        respected and data is never skipped.
        """
        url = f"{self.url}/{endpoint.lstrip('/')}"

        for attempt in range(self.MAX_RETRIES):
            response = self.session.request(method, url, **kwargs)

            # Read rate-limit headers on every response
            remaining = response.headers.get("X-RateLimit-Remaining")
            reset_ts = response.headers.get("X-RateLimit-Reset")

            if remaining is not None:
                remaining_int = int(remaining)
                if remaining_int < 100:
                    logger.warning(
                        "github_rate_limit_low",
                        remaining=remaining_int,
                        reset=reset_ts,
                    )

            # Success
            if response.status_code < 400:
                return response

            # Rate limited (403 with rate limit message, or 429)
            if response.status_code in (403, 429):
                if reset_ts:
                    wait_seconds = max(0, int(reset_ts) - int(time.time())) + 5
                else:
                    wait_seconds = min(60 * (2 ** attempt), 960)

                logger.warning(
                    "github_rate_limited",
                    status=response.status_code,
                    attempt=attempt + 1,
                    wait_seconds=wait_seconds,
                    remaining=remaining,
                )
                time.sleep(wait_seconds)
                continue

            # Other errors
            response.raise_for_status()

        # Exhausted retries
        raise RuntimeError(
            f"GitHub API request failed after {self.MAX_RETRIES} retries: "
            f"{method} {url} — last status {response.status_code}"
        )

    # ------------------------------------------------------------------
    # Branch priority
    # ------------------------------------------------------------------

    def _determine_default_branch(self, owner: str, repo: str) -> str:
        """Determine the default branch using priority rules.

        Priority:
        1. "prd" branch if it exists
        2. "production" branch if it exists
        3. Repository's default branch
        """
        try:
            # Get repo info for default branch
            repo_info = self.get_repository(owner, repo)
            repo_default = repo_info.get("default_branch", "main")

            # List branches (paginated) to check priority names
            branches: set[str] = set()
            page = 1
            while True:
                resp = self._request(
                    "GET",
                    f"repos/{owner}/{repo}/branches",
                    params={"per_page": 100, "page": page},
                )
                batch = resp.json()
                if not batch:
                    break
                branches.update(b["name"] for b in batch)
                # Check Link header for next page
                if 'rel="next"' not in resp.headers.get("Link", ""):
                    break
                page += 1

            if "prd" in branches:
                logger.info("branch_priority_selected", owner=owner, repo=repo, selected_branch="prd")
                return "prd"
            if "production" in branches:
                logger.info("branch_priority_selected", owner=owner, repo=repo, selected_branch="production")
                return "production"

            logger.info("branch_priority_selected", owner=owner, repo=repo, selected_branch=repo_default)
            return repo_default

        except Exception as e:
            logger.warning("branch_determination_failed", owner=owner, repo=repo, error=str(e))
            return "main"

    # ------------------------------------------------------------------
    # Repository operations
    # ------------------------------------------------------------------

    def get_repository(self, owner: str, repo: str) -> Dict:
        """Get repository details."""
        resp = self._request("GET", f"repos/{owner}/{repo}")
        data = resp.json()
        return {
            "id": data["id"],
            "name": data["name"],
            "full_name": data["full_name"],
            "default_branch": data.get("default_branch", "main"),
            "description": data.get("description"),
            "html_url": data["html_url"],
            "clone_url": data["clone_url"],
            "ssh_url": data.get("ssh_url"),
            "size": data.get("size", 0),
            "archived": data.get("archived", False),
            "fork": data.get("fork", False),
            "private": data.get("private", False),
        }

    def list_org_repositories(self, owner: str) -> List[Dict]:
        """List all repositories for an organization or user.

        Tries org endpoint first, falls back to user endpoint.
        Follows pagination to discover ALL repositories.
        Excludes archived repos.
        """
        repos: List[Dict] = []

        # Try org endpoint first
        endpoint = f"orgs/{owner}/repos"
        try:
            first_resp = self._request("GET", endpoint, params={"per_page": 100, "type": "all"})
            if first_resp.status_code == 404:
                raise requests.exceptions.HTTPError("Not an org")
            repos.extend(first_resp.json())
        except (requests.exceptions.HTTPError, RuntimeError):
            # Fall back to user endpoint
            endpoint = f"users/{owner}/repos"
            first_resp = self._request("GET", endpoint, params={"per_page": 100, "type": "all"})
            repos.extend(first_resp.json())

        # Follow pagination via Link headers
        link_header = first_resp.headers.get("Link", "")
        while 'rel="next"' in link_header:
            next_url = self._extract_next_url(link_header)
            if not next_url:
                break
            resp = self.session.request("GET", next_url)
            # Handle rate limits on paginated requests too
            if resp.status_code in (403, 429):
                reset_ts = resp.headers.get("X-RateLimit-Reset")
                if reset_ts:
                    wait = max(0, int(reset_ts) - int(time.time())) + 5
                else:
                    wait = 60
                logger.warning("github_rate_limited_pagination", wait_seconds=wait)
                time.sleep(wait)
                resp = self.session.request("GET", next_url)
            resp.raise_for_status()
            repos.extend(resp.json())
            link_header = resp.headers.get("Link", "")

        # Filter out archived repos
        result = []
        for r in repos:
            if r.get("archived", False):
                continue
            result.append({
                "id": r["id"],
                "name": r["name"],
                "full_name": r["full_name"],
                "default_branch": r.get("default_branch", "main"),
                "description": r.get("description"),
                "html_url": r["html_url"],
                "clone_url": r["clone_url"],
                "size": r.get("size", 0),
                "fork": r.get("fork", False),
                "private": r.get("private", False),
            })

        logger.info("github_repositories_listed", owner=owner, count=len(result))
        return result

    @staticmethod
    def _extract_next_url(link_header: str) -> Optional[str]:
        """Extract next URL from GitHub Link header."""
        for part in link_header.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
                return url
        return None

    def get_latest_commit(self, owner: str, repo: str, branch: Optional[str] = None) -> Dict:
        """Get latest commit for a branch."""
        params = {"per_page": 1}
        if branch:
            params["sha"] = branch
        resp = self._request("GET", f"repos/{owner}/{repo}/commits", params=params)
        commits = resp.json()
        if not commits:
            return {}
        c = commits[0]
        return {
            "sha": c["sha"],
            "message": c["commit"]["message"],
            "author_name": c["commit"]["author"]["name"],
            "author_email": c["commit"]["author"]["email"],
            "committed_date": c["commit"]["author"]["date"],
        }

    def list_repository_files(
        self,
        owner: str,
        repo: str,
        ref: Optional[str] = None,
        recursive: bool = True,
    ) -> List[Dict]:
        """List files in a repository using the Git Trees API.

        Uses ?recursive=1 to get the full tree in one call.
        """
        if not ref:
            repo_info = self.get_repository(owner, repo)
            ref = repo_info.get("default_branch", "main")

        params = {}
        if recursive:
            params["recursive"] = "1"

        resp = self._request("GET", f"repos/{owner}/{repo}/git/trees/{ref}", params=params)
        data = resp.json()

        return [
            {"path": item["path"], "type": item["type"], "size": item.get("size", 0)}
            for item in data.get("tree", [])
            if item["type"] == "blob"
        ]

    def get_optimal_branch_for_repository(self, owner: str, repo: str) -> str:
        """Convenience wrapper for _determine_default_branch."""
        return self._determine_default_branch(owner, repo)

    def test_connection(self) -> bool:
        """Test GitHub connection and authentication."""
        try:
            if self.token:
                resp = self._request("GET", "user")
                user = resp.json()
                logger.info("github_connection_test_successful", user=user.get("login"))
            else:
                resp = self._request("GET", "rate_limit")
                logger.info("github_connection_test_successful_unauthenticated")
            return True
        except Exception as e:
            logger.error("github_connection_test_failed", error=str(e))
            return False
