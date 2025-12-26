"""
Deduplication Script for Projects

This script finds and merges duplicate project records in the database.

Duplicates occur when:
1. .sln files create projects with relative paths + solution_id + project_guid
2. .csproj files create projects with absolute paths + null solution_id + null project_guid

The script:
1. Finds duplicate projects by (name, repository_id)
2. Merges metadata from both records (prefer .sln data for solution_id/project_guid)
3. Updates all symbol references to the merged project
4. Deletes duplicate records
"""
import asyncio
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from src.database.models import Project, Symbol
from src.config.settings import settings
from src.utils.logging_config import get_logger
from pathlib import Path
from typing import List, Dict, Tuple

logger = get_logger(__name__)


class ProjectDeduplicator:
    """Deduplicate project records in the database."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.stats = {
            'projects_examined': 0,
            'duplicates_found': 0,
            'projects_merged': 0,
            'symbols_updated': 0,
            'projects_deleted': 0
        }
    
    async def find_duplicate_groups(self, repository_id: int) -> List[Tuple[str, List[Project]]]:
        """
        Find groups of duplicate projects by (name, repository_id).
        
        Args:
            repository_id: Repository to check
            
        Returns:
            List of (project_name, [duplicate_projects])
        """
        # Get all projects for this repository
        stmt = select(Project).where(Project.repository_id == repository_id)
        result = await self.session.execute(stmt)
        projects = result.scalars().all()
        
        self.stats['projects_examined'] = len(projects)
        
        # Group by name
        groups: Dict[str, List[Project]] = {}
        for project in projects:
            if project.name not in groups:
                groups[project.name] = []
            groups[project.name].append(project)
        
        # Filter only groups with duplicates
        duplicate_groups = [
            (name, projs) for name, projs in groups.items()
            if len(projs) > 1
        ]
        
        self.stats['duplicates_found'] = len(duplicate_groups)
        
        return duplicate_groups
    
    def _choose_primary_project(self, projects: List[Project]) -> Project:
        """
        Choose the primary project from duplicates.
        
        Prefer projects with:
        1. solution_id (from .sln parsing)
        2. project_guid (from .sln parsing)
        3. Most complete metadata
        
        Args:
            projects: List of duplicate projects
            
        Returns:
            The primary project to keep
        """
        # Sort by preference
        def sort_key(p: Project):
            has_solution = 1 if p.solution_id else 0
            has_guid = 1 if p.project_guid else 0
            has_assembly = 1 if p.assembly_name else 0
            has_framework = 1 if p.target_framework else 0
            
            # Higher score = better
            score = (
                has_solution * 1000 +
                has_guid * 100 +
                has_assembly * 10 +
                has_framework * 1
            )
            return score
        
        projects_sorted = sorted(projects, key=sort_key, reverse=True)
        return projects_sorted[0]
    
    def _merge_metadata(self, primary: Project, others: List[Project]):
        """
        Merge metadata from duplicate projects into the primary.
        
        Strategy:
        - Keep solution_id and project_guid from primary (most likely from .sln)
        - Fill in missing fields from others (like assembly_name from .csproj)
        
        Args:
            primary: Primary project to update
            others: Other duplicate projects
        """
        for other in others:
            # Merge metadata if primary is missing it
            if not primary.assembly_name and other.assembly_name:
                primary.assembly_name = other.assembly_name
            if not primary.target_framework and other.target_framework:
                primary.target_framework = other.target_framework
            if not primary.output_type and other.output_type:
                primary.output_type = other.output_type
            if not primary.root_namespace and other.root_namespace:
                primary.root_namespace = other.root_namespace
            if not primary.define_constants and other.define_constants:
                primary.define_constants = other.define_constants
            if not primary.lang_version and other.lang_version:
                primary.lang_version = other.lang_version
            if not primary.nullable_context and other.nullable_context:
                primary.nullable_context = other.nullable_context
                
            # Prefer absolute paths
            if other.file_path and Path(other.file_path).is_absolute():
                if not Path(primary.file_path).is_absolute():
                    primary.file_path = other.file_path
    
    async def merge_duplicate_group(
        self,
        name: str,
        projects: List[Project]
    ) -> Tuple[int, int]:
        """
        Merge a group of duplicate projects.
        
        Args:
            name: Project name
            projects: List of duplicate projects
            
        Returns:
            (symbols_updated, projects_deleted)
        """
        if len(projects) <= 1:
            return 0, 0
        
        # Choose primary project
        primary = self._choose_primary_project(projects)
        others = [p for p in projects if p.id != primary.id]
        
        logger.info(
            "merging_duplicate_projects",
            name=name,
            primary_id=primary.id,
            duplicate_ids=[p.id for p in others]
        )
        
        # Merge metadata
        self._merge_metadata(primary, others)
        self.session.add(primary)
        
        # Update symbols to point to primary
        symbols_updated = 0
        for other in others:
            # Find symbols pointing to this duplicate
            stmt = select(Symbol).where(Symbol.project_id == other.id)
            result = await self.session.execute(stmt)
            symbols = result.scalars().all()
            
            for symbol in symbols:
                symbol.project_id = primary.id
                self.session.add(symbol)
                symbols_updated += 1
        
        # Delete duplicates
        projects_deleted = 0
        for other in others:
            await self.session.delete(other)
            projects_deleted += 1
        
        await self.session.flush()
        
        logger.info(
            "merged_duplicate_projects",
            name=name,
            primary_id=primary.id,
            symbols_updated=symbols_updated,
            projects_deleted=projects_deleted
        )
        
        return symbols_updated, projects_deleted
    
    async def deduplicate_repository(self, repository_id: int):
        """
        Deduplicate all projects in a repository.
        
        Args:
            repository_id: Repository ID
        """
        logger.info("starting_deduplication", repository_id=repository_id)
        
        # Find duplicate groups
        duplicate_groups = await self.find_duplicate_groups(repository_id)
        
        if not duplicate_groups:
            logger.info("no_duplicates_found", repository_id=repository_id)
            return
        
        logger.info(
            "found_duplicate_groups",
            repository_id=repository_id,
            groups=len(duplicate_groups)
        )
        
        # Merge each group
        for name, projects in duplicate_groups:
            symbols_updated, projects_deleted = await self.merge_duplicate_group(name, projects)
            self.stats['symbols_updated'] += symbols_updated
            self.stats['projects_deleted'] += projects_deleted
            self.stats['projects_merged'] += 1
        
        # Commit changes
        await self.session.commit()
        
        logger.info(
            "deduplication_completed",
            repository_id=repository_id,
            stats=self.stats
        )


async def main():
    """Main entry point."""
    # Create async engine
    engine = create_async_engine(
        settings.database_url.replace('postgresql://', 'postgresql+asyncpg://'),
        echo=False
    )
    
    # Create session
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        deduplicator = ProjectDeduplicator(session)
        
        # You can specify repository_id here
        # For now, we'll process repository 3 as mentioned
        repository_id = 3
        
        print(f"Starting deduplication for repository {repository_id}...")
        await deduplicator.deduplicate_repository(repository_id)
        
        print("\nDeduplication Summary:")
        print(f"  Projects examined: {deduplicator.stats['projects_examined']}")
        print(f"  Duplicate groups found: {deduplicator.stats['duplicates_found']}")
        print(f"  Projects merged: {deduplicator.stats['projects_merged']}")
        print(f"  Symbols updated: {deduplicator.stats['symbols_updated']}")
        print(f"  Projects deleted: {deduplicator.stats['projects_deleted']}")
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
