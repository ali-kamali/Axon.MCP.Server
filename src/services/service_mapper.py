"""Service mapper for resolving Docker service names to repositories.

This service provides:
1. Automatic mapping of Docker service names to repositories
2. Service URL resolution (http://service-name:port → repository)
3. Multiple mapping strategies (exact name, image match, path match)
"""

from typing import Optional, List, Dict, Any
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path

from src.database.models import (
    DockerService,
    ServiceRepositoryMapping,
    Repository,
)
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class ServiceMapper:
    """Maps Docker service names to repositories for URL resolution."""

    def __init__(self, db: AsyncSession):
        """
        Initialize the service mapper.
        
        Args:
            db: AsyncSession for database operations
        """
        self.db = db
        self._service_cache: Dict[str, int] = {}  # service_name -> repository_id

    async def map_service_to_repository(
        self,
        service_name: str,
        refresh_cache: bool = False
    ) -> Optional[Repository]:
        """
        Map a Docker service name to its repository.
        
        Args:
            service_name: Name of the Docker service
            refresh_cache: If True, bypass cache and query database
            
        Returns:
            Repository object if mapping found, None otherwise
        """
        # Check cache first
        if not refresh_cache and service_name in self._service_cache:
            repo_id = self._service_cache[service_name]
            result = await self.db.execute(
                select(Repository).where(Repository.id == repo_id)
            )
            return result.scalar_one_or_none()
        
        # Query database for mapping
        result = await self.db.execute(
            select(ServiceRepositoryMapping, Repository)
            .join(Repository, ServiceRepositoryMapping.target_repository_id == Repository.id)
            .where(ServiceRepositoryMapping.service_name == service_name)
            .order_by(ServiceRepositoryMapping.confidence.desc())
            .limit(1)
        )
        
        row = result.first()
        if row:
            mapping, repository = row
            # Update cache
            self._service_cache[service_name] = repository.id
            logger.info("service_mapped_from_cache",
                       service_name=service_name,
                       repository=repository.name,
                       confidence=mapping.confidence)
            return repository
        
        logger.debug("service_not_mapped", service_name=service_name)
        return None

    async def resolve_service_url(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Resolve a service URL to its repository.
        
        Args:
            url: Service URL (e.g., "http://auth-service:8080/api/login")
            
        Returns:
            Dict with repository and resolved URL, or None if not resolvable
        """
        service_name = self._extract_service_name(url)
        if not service_name:
            return None
        
        repository = await self.map_service_to_repository(service_name)
        if not repository:
            return None
        
        return {
            "service_name": service_name,
            "repository": repository,
            "original_url": url,
            "resolved": True
        }

    def _extract_service_name(self, url: str) -> Optional[str]:
        """
        Extract service name from URL.
        
        Examples:
            http://auth-service:8080/api/login → auth-service
            auth-service:8080 → auth-service
            http://auth-service/api → auth-service
        """
        import re
        
        # Remove protocol
        url_without_protocol = re.sub(r'^https?://', '', url)
        
        # Extract host part (before first / or :)
        match = re.match(r'^([^/:]+)', url_without_protocol)
        if match:
            return match.group(1)
        
        return None

    async def auto_map_services(
        self,
        repository_ids: Optional[List[int]] = None
    ) -> int:
        """
        Automatically map Docker services to repositories.
        
        Uses multiple strategies:
        1. Exact name match: service name == repository name
        2. Image match: Docker image name matches repository name
        3. Path match: service name appears in repository path
        
        Args:
            repository_ids: Optional list of repository IDs to process
            
        Returns:
            Number of mappings created
        """
        logger.info("auto_mapping_services_started", repository_ids=repository_ids)
        
        # Get all Docker services
        query = select(DockerService)
        if repository_ids:
            query = query.where(DockerService.repository_id.in_(repository_ids))
        
        result = await self.db.execute(query)
        services = result.scalars().all()
        
        # Get all repositories
        repo_query = select(Repository)
        if repository_ids:
            repo_query = repo_query.where(Repository.id.in_(repository_ids))
        
        repo_result = await self.db.execute(repo_query)
        repositories = repo_result.scalars().all()
        
        mappings_created = 0
        
        for service in services:
            # Try each mapping strategy
            mapping = await self._find_best_mapping(service, repositories)
            
            if mapping:
                # Check if mapping already exists
                existing = await self.db.execute(
                    select(ServiceRepositoryMapping).where(
                        and_(
                            ServiceRepositoryMapping.docker_service_id == service.id,
                            ServiceRepositoryMapping.target_repository_id == mapping["repository_id"]
                        )
                    )
                )
                
                if not existing.scalar_one_or_none():
                    # Create new mapping
                    new_mapping = ServiceRepositoryMapping(
                        docker_service_id=service.id,
                        service_name=service.service_name,
                        target_repository_id=mapping["repository_id"],
                        confidence=mapping["confidence"],
                        mapping_method=mapping["method"],
                        mapping_metadata=mapping["metadata"],
                        is_manual=0
                    )
                    self.db.add(new_mapping)
                    mappings_created += 1
                    
                    logger.info("service_mapping_created",
                               service_name=service.service_name,
                               repository_id=mapping["repository_id"],
                               method=mapping["method"],
                               confidence=mapping["confidence"])
        
        await self.db.commit()
        logger.info("auto_mapping_services_completed", mappings_created=mappings_created)
        
        return mappings_created

    async def _find_best_mapping(
        self,
        service: DockerService,
        repositories: List[Repository]
    ) -> Optional[Dict[str, Any]]:
        """
        Find the best repository mapping for a service.
        
        Args:
            service: DockerService to map
            repositories: List of available repositories
            
        Returns:
            Mapping dict with repository_id, confidence, method, and metadata
        """
        best_mapping = None
        best_confidence = 0
        
        for repo in repositories:
            # Strategy 1: Exact name match
            if service.service_name.lower() == repo.name.lower():
                confidence = 100
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_mapping = {
                        "repository_id": repo.id,
                        "confidence": confidence,
                        "method": "exact_name",
                        "metadata": {"matched_field": "name"}
                    }
                    continue
            
            # Strategy 2: Image name match
            if service.image:
                image_name = self._extract_image_name(service.image)
                if image_name and image_name.lower() == repo.name.lower():
                    confidence = 95
                    if confidence > best_confidence:
                        best_confidence = confidence
                        best_mapping = {
                            "repository_id": repo.id,
                            "confidence": confidence,
                            "method": "image_match",
                            "metadata": {"image": service.image, "matched_name": image_name}
                        }
                        continue
            
            # Strategy 3: Path match (service name in repository path)
            if service.service_name.lower() in repo.path_with_namespace.lower():
                confidence = 80
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_mapping = {
                        "repository_id": repo.id,
                        "confidence": confidence,
                        "method": "path_match",
                        "metadata": {"path": repo.path_with_namespace}
                    }
                    continue
            
            # Strategy 4: Fuzzy name match (partial match)
            if service.service_name.lower() in repo.name.lower() or repo.name.lower() in service.service_name.lower():
                confidence = 70
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_mapping = {
                        "repository_id": repo.id,
                        "confidence": confidence,
                        "method": "fuzzy_name",
                        "metadata": {"service_name": service.service_name, "repo_name": repo.name}
                    }
        
        # Only return mappings with confidence >= 70
        if best_mapping and best_mapping["confidence"] >= 70:
            return best_mapping
        
        return None

    def _extract_image_name(self, image: str) -> Optional[str]:
        """
        Extract image name from Docker image string.
        
        Examples:
            auth-service:latest → auth-service
            myregistry.com/auth-service:v1.0 → auth-service
            auth-service → auth-service
        """
        # Remove registry prefix
        if "/" in image:
            image = image.split("/")[-1]
        
        # Remove tag
        if ":" in image:
            image = image.split(":")[0]
        
        return image if image else None

    async def create_manual_mapping(
        self,
        service_name: str,
        repository_id: int,
        docker_service_id: Optional[int] = None
    ) -> ServiceRepositoryMapping:
        """
        Create a manual service-to-repository mapping.
        
        Args:
            service_name: Name of the Docker service
            repository_id: Target repository ID
            docker_service_id: Optional Docker service ID
            
        Returns:
            Created ServiceRepositoryMapping
        """
        mapping = ServiceRepositoryMapping(
            docker_service_id=docker_service_id,
            service_name=service_name,
            target_repository_id=repository_id,
            confidence=100,
            mapping_method="manual",
            mapping_metadata={"created_by": "user"},
            is_manual=1
        )
        
        self.db.add(mapping)
        await self.db.commit()
        
        # Update cache
        self._service_cache[service_name] = repository_id
        
        logger.info("manual_mapping_created",
                   service_name=service_name,
                   repository_id=repository_id)
        
        return mapping

    async def get_all_mappings(
        self,
        repository_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all service mappings, optionally filtered by repository.
        
        Args:
            repository_id: Optional repository ID to filter by
            
        Returns:
            List of mapping dictionaries
        """
        query = select(ServiceRepositoryMapping, Repository).join(
            Repository,
            ServiceRepositoryMapping.target_repository_id == Repository.id
        )
        
        if repository_id:
            query = query.where(ServiceRepositoryMapping.target_repository_id == repository_id)
        
        result = await self.db.execute(query)
        
        mappings = []
        for mapping, repository in result:
            mappings.append({
                "id": mapping.id,
                "service_name": mapping.service_name,
                "repository_id": repository.id,
                "repository_name": repository.name,
                "confidence": mapping.confidence,
                "method": mapping.mapping_method,
                "is_manual": bool(mapping.is_manual),
                "metadata": mapping.mapping_metadata
            })
        
        return mappings
