"""
EF Core Entity Analyzer

Analyzes Entity Framework Core entities during repository sync and stores mappings in database.
"""
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models import EfEntity
from src.parsers.roslyn_integration import RoslynAnalyzer
from src.utils.logging_config import get_logger
from datetime import datetime

logger = get_logger(__name__)


class EfCoreAnalyzer:
    """Analyzes EF Core entities and stores them in the database."""
    
    def __init__(self, roslyn_analyzer: RoslynAnalyzer):
        """
        Initialize EF Core analyzer.
        
        Args:
            roslyn_analyzer: Roslyn analyzer instance for C# parsing
        """
        self.roslyn = roslyn_analyzer
    
    async def analyze_repository(self, session: AsyncSession, repo_id: int, repo_path: str) -> Dict[str, Any]:
        """
        Analyze all EF Core entities in a repository.
        
        Args:
            session: Database session
            repo_id: Repository ID
            repo_path: Path to repository
            
        Returns:
            Dictionary with analysis results
        """
        try:
            # Find .csproj files that might contain EF entities
            ef_projects = await self._find_ef_projects(repo_path)
            
            if not ef_projects:
                logger.info(
                    "no_ef_projects_found",
                    repository_id=repo_id,
                    message="No EF Core projects detected"
                )
                return {"entities_found": 0, "projects_analyzed": 0}
            
            total_entities = 0
            
            for project_path in ef_projects:
                logger.info(
                    "analyzing_ef_project",
                    repository_id=repo_id,
                    project=str(project_path)
                )
                
                # Load project in Roslyn
                success = await self.roslyn.open_project(str(project_path))
                if not success:
                    logger.warning(
                        "failed_to_load_project",
                        repository_id=repo_id,
                        project=str(project_path)
                    )
                    continue
                
                # Analyze entities
                entities = await self._analyze_project_entities(session, repo_id, str(project_path))
                total_entities += len(entities)
            
            logger.info(
                "ef_analysis_completed",
                repository_id=repo_id,
                entities_found=total_entities,
                projects_analyzed=len(ef_projects)
            )
            
            return {
                "entities_found": total_entities,
                "projects_analyzed": len(ef_projects)
            }
            
        except Exception as e:
            logger.error(
                "ef_analysis_failed",
                repository_id=repo_id,
                error=str(e),
                error_type=type(e).__name__
            )
            return {"entities_found": 0, "projects_analyzed": 0, "error": str(e)}
    
    async def _find_ef_projects(self, repo_path: str) -> List[Path]:
        """
        Find .csproj files that likely contain EF Core entities.
        
        Args:
            repo_path: Path to repository
            
        Returns:
            List of .csproj file paths
        """
        ef_projects = []
        repo_path_obj = Path(repo_path)
        
        # Find all .csproj files
        for csproj in repo_path_obj.rglob("*.csproj"):
            # Read .csproj to check for EF Core references
            try:
                content = csproj.read_text(encoding='utf-8-sig', errors='ignore')
                
                # Simple heuristic: check for EF Core package references
                if any(pkg in content for pkg in [
                    "Microsoft.EntityFrameworkCore",
                    "EntityFrameworkCore",
                    "EFCore"
                ]):
                    ef_projects.append(csproj)
                    logger.debug(
                        "ef_project_detected",
                        project=str(csproj)
                    )
            except Exception as e:
                logger.warning(
                    "failed_to_read_csproj",
                    project=str(csproj),
                    error=str(e)
                )
                continue
        
        return ef_projects
    
    async def _analyze_project_entities(
        self, 
        session: AsyncSession, 
        repo_id: int, 
        project_path: str
    ) -> List[EfEntity]:
        """
        Analyze entities in a specific project.
        
        Args:
            session: Database session
            repo_id: Repository ID
            project_path: Path to .csproj file
            
        Returns:
            List of created/updated EfEntity records
        """
        entities = []
        
        try:
            # Call Roslyn analyzer to get entity mappings
            result = await self.roslyn.analyze_ef_entities(project_path)
            
            if not result or not result.get("success"):
                logger.warning(
                    "ef_entity_analysis_failed",
                    project=project_path,
                    error=result.get("error") if result else "No result"
                )
                return entities
            
            entity_data = result.get("entities", [])
            
            for entity_info in entity_data:
                # Store or update entity in database
                entity = await self._store_entity(session, repo_id, entity_info)
                if entity:
                    entities.append(entity)
                    # Flush to catch constraint violations immediately
                    try:
                        await session.flush()
                    except Exception as flush_error:
                        # If this specific entity causes a constraint violation, roll it back
                        await session.rollback()
                        logger.warning(
                            "ef_entity_constraint_violation",
                            entity_name=entity_info.get("entity"),
                            namespace=entity_info.get("namespace"),
                            error=str(flush_error)
                        )
                        # Remove from entities list since it wasn't saved
                        entities.pop()
            
            await session.commit()
            
        except Exception as e:
            logger.error(
                "failed_to_analyze_project_entities",
                project=project_path,
                error=str(e),
                error_type=type(e).__name__
            )
            await session.rollback()
        
        return entities
    
    async def _store_entity(
        self,
        session: AsyncSession,
        repo_id: int,
        entity_info: Dict[str, Any]
    ) -> Optional[EfEntity]:
        """
        Store or update an entity mapping in the database.
        
        Args:
            session: Database session
            repo_id: Repository ID
            entity_info: Entity information from Roslyn analyzer
            
        Returns:
            EfEntity record or None
        """
        try:
            entity_name = entity_info.get("entity")
            if not entity_name:
                return None
            
            # Check if entity already exists
            from sqlalchemy import select
            stmt = select(EfEntity).where(
                EfEntity.repository_id == repo_id,
                EfEntity.entity_name == entity_name
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                # Update existing entity
                existing.namespace = entity_info.get("namespace")
                existing.table_name = entity_info.get("table_name")
                existing.schema_name = entity_info.get("schema_name") or "dbo"
                existing.primary_keys = entity_info.get("primary_keys")
                existing.properties = entity_info.get("properties")
                existing.relationships = entity_info.get("relationships")
                existing.raw_mapping = entity_info.get("raw_mapping")
                existing.updated_at = datetime.utcnow()
                
                logger.debug(
                    "ef_entity_updated",
                    entity_name=entity_name,
                    table_name=existing.table_name
                )
                
                return existing
            else:
                # Create new entity
                entity = EfEntity(
                    repository_id=repo_id,
                    entity_name=entity_name,
                    namespace=entity_info.get("namespace"),
                    table_name=entity_info.get("table_name"),
                    schema_name=entity_info.get("schema_name") or "dbo",  # Default to dbo if not specified
                    primary_keys=entity_info.get("primary_keys"),
                    properties=entity_info.get("properties"),
                    relationships=entity_info.get("relationships"),
                    raw_mapping=entity_info.get("raw_mapping"),
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                
                session.add(entity)
                
                logger.debug(
                    "ef_entity_created",
                    entity_name=entity_name,
                    table_name=entity.table_name
                )
                
                return entity
                
        except Exception as e:
            logger.error(
                "failed_to_store_entity",
                entity_name=entity_info.get("entity"),
                error=str(e),
                error_type=type(e).__name__
            )
            return None
