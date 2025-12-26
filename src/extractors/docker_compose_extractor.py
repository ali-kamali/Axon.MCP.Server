"""Docker Compose extractor for processing docker-compose.yml files.

This extractor:
1. Parses docker-compose.yml files
2. Stores services in the database
3. Triggers automatic service-to-repository mapping
"""

from typing import List, Dict, Any, Optional
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from src.database.models import DockerService, File, Repository
from src.parsers.docker_compose_parser import DockerComposeParser
from src.services.service_mapper import ServiceMapper
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class DockerComposeExtractor:
    """Extracts Docker Compose services and stores them in the database."""

    def __init__(self, session: AsyncSession):
        """
        Initialize Docker Compose extractor.
        
        Args:
            session: Database session
        """
        self.session = session
        self.parser = DockerComposeParser()
        self.service_mapper = ServiceMapper(session)

    async def extract_from_file(
        self,
        file_id: int,
        repo_path: Path
    ) -> int:
        """
        Extract Docker services from a docker-compose.yml file.
        
        Args:
            file_id: Database file ID
            repo_path: Path to repository root
            
        Returns:
            Number of services extracted
        """
        # Get file info
        result = await self.session.execute(
            select(File).where(File.id == file_id)
        )
        file_obj = result.scalar_one_or_none()
        
        if not file_obj:
            logger.warning("file_not_found", file_id=file_id)
            return 0
        
        # Check if this is a docker-compose file
        if not self._is_docker_compose_file(file_obj.path):
            return 0
        
        try:
            # Parse docker-compose.yml
            file_path = repo_path / file_obj.path
            parsed_data = await self.parser.parse_file(file_path)
            
            if not parsed_data or not parsed_data.get("services"):
                logger.info("no_services_found", file_path=str(file_path))
                return 0
            
            # Delete existing services for this file (for re-parsing)
            await self.session.execute(
                delete(DockerService).where(
                    DockerService.repository_id == file_obj.repository_id,
                    DockerService.file_path == file_obj.path
                )
            )
            
            # Store services
            services_created = 0
            for service_data in parsed_data["services"]:
                docker_service = self._create_docker_service(
                    service_data,
                    file_obj.repository_id,
                    file_obj.path
                )
                self.session.add(docker_service)
                services_created += 1
            
            await self.session.flush()
            
            logger.info("docker_services_extracted",
                       file_id=file_id,
                       services_count=services_created)
            
            return services_created
            
        except Exception as e:
            logger.error("docker_compose_extraction_failed",
                        file_id=file_id,
                        error=str(e))
            return 0

    def _is_docker_compose_file(self, file_path: str) -> bool:
        """Check if file is a docker-compose file."""
        file_path_lower = file_path.lower()
        return (
            file_path_lower.endswith('docker-compose.yml') or
            file_path_lower.endswith('docker-compose.yaml') or
            'docker-compose' in file_path_lower
        )

    def _create_docker_service(
        self,
        service_data: Dict[str, Any],
        repository_id: int,
        file_path: str
    ) -> DockerService:
        """
        Create DockerService model from parsed service data.
        
        Args:
            service_data: Parsed service dictionary
            repository_id: Repository ID
            file_path: Path to docker-compose.yml file
            
        Returns:
            DockerService model
        """
        # Extract build configuration
        build_config = service_data.get("build")
        build_context = None
        dockerfile = None
        build_args = None
        
        if build_config:
            build_context = build_config.get("context")
            dockerfile = build_config.get("dockerfile")
            build_args = build_config.get("args")
        
        # Convert command and entrypoint to string if they're lists
        command = service_data.get("command")
        if isinstance(command, list):
            command = " ".join(str(c) for c in command)
        
        entrypoint = service_data.get("entrypoint")
        if isinstance(entrypoint, list):
            entrypoint = " ".join(str(e) for e in entrypoint)
        
        return DockerService(
            repository_id=repository_id,
            file_path=file_path,
            service_name=service_data["service_name"],
            image=service_data.get("image"),
            container_name=service_data.get("container_name"),
            build_context=build_context,
            dockerfile=dockerfile,
            build_args=build_args,
            ports=service_data.get("ports"),
            expose=service_data.get("expose"),
            networks=service_data.get("networks"),
            depends_on=service_data.get("depends_on"),
            links=service_data.get("links"),
            environment=service_data.get("environment"),
            volumes=service_data.get("volumes"),
            command=command,
            entrypoint=entrypoint,
            working_dir=service_data.get("working_dir"),
            user=service_data.get("user"),
            restart=service_data.get("restart"),
            healthcheck=service_data.get("healthcheck"),
            labels=service_data.get("labels"),
            service_metadata={
                "extra_hosts": service_data.get("extra_hosts"),
            }
        )

    async def extract_from_repository(
        self,
        repository_id: int,
        repo_path: Path
    ) -> int:
        """
        Extract Docker services from all docker-compose files in a repository.
        
        Args:
            repository_id: Repository ID
            repo_path: Path to repository root
            
        Returns:
            Total number of services extracted
        """
        # Find all docker-compose files
        result = await self.session.execute(
            select(File).where(File.repository_id == repository_id)
        )
        files = result.scalars().all()
        
        total_services = 0
        for file_obj in files:
            if self._is_docker_compose_file(file_obj.path):
                services_count = await self.extract_from_file(file_obj.id, repo_path)
                total_services += services_count
        
        # Trigger automatic service mapping
        if total_services > 0:
            logger.info("triggering_service_mapping", repository_id=repository_id)
            mappings_created = await self.service_mapper.auto_map_services([repository_id])
            logger.info("service_mapping_completed",
                       repository_id=repository_id,
                       mappings_created=mappings_created)
        
        return total_services
