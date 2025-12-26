"""Incremental repository synchronization using git diff."""

import asyncio
import hashlib
from pathlib import Path
from typing import List, Optional, Set
from dataclasses import dataclass
from datetime import datetime
from git import Repo, GitCommandError
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Repository, File, Symbol, Relation, Chunk, Embedding
from src.config.enums import RepositoryStatusEnum, SymbolKindEnum, LanguageEnum
from src.parsers import parse_file
from src.extractors.knowledge_extractor import KnowledgeExtractor
from src.extractors.relationship_builder import RelationshipBuilder
from src.embeddings.generator import EmbeddingGenerator
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class FileChange:
    """Represents a file change in git diff."""
    path: str
    change_type: str  # 'A' (added), 'M' (modified), 'D' (deleted), 'R' (renamed)
    old_path: Optional[str] = None  # For renames


class IncrementalSyncWorker:
    """Handles incremental repository synchronization."""
    
    def __init__(self, session: AsyncSession, repo_cache_dir: Path):
        """
        Initialize incremental sync worker.
        
        Args:
            session: Database session
            repo_cache_dir: Directory where repositories are cached
        """
        self.session = session
        self.repo_cache_dir = repo_cache_dir
    
    async def sync_repository_incremental(
        self,
        repository_id: int,
        repo: Repository,
        repo_path: Path
    ) -> dict:
        """
        Perform incremental sync of repository.
        
        Strategy:
        1. Get last synced commit SHA
        2. Fetch latest commit from remote
        3. If same, skip sync
        4. Get changed files using git diff
        5. Parse only changed files
        6. Update relationships for affected files
        
        Args:
            repository_id: Repository ID
            repo: Repository model
            repo_path: Path to repository on disk
            
        Returns:
            Dict with sync results
        """
        try:
            # Open git repository
            git_repo = Repo(repo_path)
            
            # Get latest commit
            latest_commit = git_repo.head.commit.hexsha
            last_commit = repo.last_commit_sha
            
            # Check if repository is up to date
            if last_commit == latest_commit:
                logger.info(
                    "repository_up_to_date",
                    repository_id=repository_id,
                    commit=latest_commit
                )
                return {
                    "status": "up_to_date",
                    "repository_id": repository_id,
                    "commit": latest_commit,
                    "files_changed": 0
                }
            
            logger.info(
                "repository_has_changes",
                repository_id=repository_id,
                from_commit=last_commit,
                to_commit=latest_commit
            )
            
            # Get changed files
            changed_files = self._get_changed_files(git_repo, last_commit, latest_commit)
            
            logger.info(
                "incremental_sync_detected_changes",
                repository_id=repository_id,
                files_changed=len(changed_files)
            )
            
            # Process changes
            files_processed = 0
            files_deleted = 0
            files_added = 0
            files_modified = 0
            
            for file_change in changed_files:
                if file_change.change_type == 'D':
                    # Deleted file
                    await self._delete_file_data(repository_id, file_change.path)
                    files_deleted += 1
                elif file_change.change_type in ['A', 'M']:
                    # Added or modified file
                    full_path = repo_path / file_change.path
                    if full_path.exists():
                        await self._reparse_file(repository_id, file_change.path, full_path)
                        if file_change.change_type == 'A':
                            files_added += 1
                        else:
                            files_modified += 1
                        files_processed += 1
                elif file_change.change_type == 'R':
                    # Renamed file
                    if file_change.old_path:
                        await self._handle_rename(
                            repository_id,
                            file_change.old_path,
                            file_change.path,
                            repo_path / file_change.path
                        )
                        files_modified += 1
                        files_processed += 1
            
            # Update repository metadata
            repo.last_commit_sha = latest_commit
            repo.last_synced_at = datetime.utcnow()
            await self.session.commit()
            
            logger.info(
                "incremental_sync_completed",
                repository_id=repository_id,
                files_processed=files_processed,
                files_added=files_added,
                files_modified=files_modified,
                files_deleted=files_deleted
            )
            
            return {
                "status": "success",
                "repository_id": repository_id,
                "commit": latest_commit,
                "files_changed": len(changed_files),
                "files_processed": files_processed,
                "files_added": files_added,
                "files_modified": files_modified,
                "files_deleted": files_deleted
            }
            
        except Exception as e:
            logger.error(
                "incremental_sync_failed",
                repository_id=repository_id,
                error=str(e),
                exc_info=True
            )
            raise
    
    def _get_changed_files(
        self,
        git_repo: Repo,
        from_commit: Optional[str],
        to_commit: str
    ) -> List[FileChange]:
        """
        Get list of changed files between commits.
        
        Args:
            git_repo: GitPython Repo object
            from_commit: Starting commit SHA (None for initial sync)
            to_commit: Ending commit SHA
            
        Returns:
            List of file changes
        """
        changes = []
        
        try:
            if not from_commit:
                # Initial sync - all files are "added"
                for item in git_repo.tree(to_commit).traverse():
                    if item.type == 'blob':  # File (not directory)
                        changes.append(FileChange(
                            path=item.path,
                            change_type='A'
                        ))
            else:
                # Get diff between commits
                diff = git_repo.commit(from_commit).diff(to_commit)
                
                # Added files
                for diff_added in diff.iter_change_type('A'):
                    changes.append(FileChange(
                        path=diff_added.b_path,
                        change_type='A'
                    ))
                
                # Modified files
                for diff_modified in diff.iter_change_type('M'):
                    changes.append(FileChange(
                        path=diff_modified.b_path,
                        change_type='M'
                    ))
                
                # Deleted files
                for diff_deleted in diff.iter_change_type('D'):
                    changes.append(FileChange(
                        path=diff_deleted.a_path,
                        change_type='D'
                    ))
                
                # Renamed files
                for diff_renamed in diff.iter_change_type('R'):
                    changes.append(FileChange(
                        path=diff_renamed.b_path,
                        change_type='R',
                        old_path=diff_renamed.a_path
                    ))
        
        except GitCommandError as e:
            logger.error("git_diff_failed", error=str(e))
            raise
        
        return changes
    
    async def _delete_file_data(self, repository_id: int, file_path: str):
        """
        Delete all data for a file.
        
        Args:
            repository_id: Repository ID
            file_path: Path to file within repository
        """
        logger.info("deleting_file_data", repository_id=repository_id, file_path=file_path)
        
        # Get file record
        result = await self.session.execute(
            select(File).where(
                File.repository_id == repository_id,
                File.path == file_path
            )
        )
        file_record = result.scalar_one_or_none()
        
        if file_record:
            # Delete file (cascades to symbols, chunks, embeddings via foreign keys)
            await self.session.delete(file_record)
            await self.session.commit()
            
            logger.info("file_data_deleted", repository_id=repository_id, file_path=file_path)
    
    async def _reparse_file(
        self,
        repository_id: int,
        file_path: str,
        full_file_path: Path
    ):
        """
        Re-parse a single file and update all related data.
        
        Args:
            repository_id: Repository ID
            file_path: Relative path within repository
            full_file_path: Full path to file on disk
        """
        logger.info("reparsing_file", repository_id=repository_id, file_path=file_path)
        
        try:
            # Get existing file record
            result = await self.session.execute(
                select(File).where(
                    File.repository_id == repository_id,
                    File.path == file_path
                )
            )
            file_record = result.scalar_one_or_none()
            
            if file_record:
                # Delete existing symbols for this file
                # This will cascade to relations, chunks, and embeddings
                await self.session.execute(
                    delete(Symbol).where(Symbol.file_id == file_record.id)
                )
                await self.session.commit()
            else:
                # Create new file record
                file_record = await self._create_file_record(repository_id, file_path, full_file_path)
            
            # Parse file
            parse_result = await asyncio.to_thread(parse_file, full_file_path)
            
            # Extract knowledge
            extractor = KnowledgeExtractor(self.session)
            extraction_result = await extractor.extract_and_persist(
                parse_result,
                file_record.id
            )
            
            # Update file metadata
            try:
                content = full_file_path.read_text(errors='ignore')
                file_record.content_hash = hashlib.sha256(content.encode('utf-8', errors='ignore')).hexdigest()
            except Exception:
                pass

            file_record.symbol_count = extraction_result.symbols_extracted
            file_record.line_count = parse_result.parse_duration_ms  # Store actual line count if available
            
            await self.session.commit()
            
            logger.info(
                "file_reparsed",
                repository_id=repository_id,
                file_path=file_path,
                symbols_extracted=extraction_result.symbols_extracted
            )
            
            return file_record
            
        except Exception as e:
            logger.error(
                "file_reparse_failed",
                repository_id=repository_id,
                file_path=file_path,
                error=str(e),
                exc_info=True
            )
            raise
    
    async def _handle_rename(
        self,
        repository_id: int,
        old_path: str,
        new_path: str,
        full_file_path: Path
    ):
        """
        Handle file rename.
        
        Args:
            repository_id: Repository ID
            old_path: Old file path
            new_path: New file path
            full_file_path: Full path to new file
        """
        logger.info(
            "handling_file_rename",
            repository_id=repository_id,
            old_path=old_path,
            new_path=new_path
        )
        
        # Get old file record
        result = await self.session.execute(
            select(File).where(
                File.repository_id == repository_id,
                File.path == old_path
            )
        )
        file_record = result.scalar_one_or_none()
        
        if file_record:
            # Update path
            file_record.path = new_path
            await self.session.commit()
            
            # Reparse to update line numbers and symbols
            await self._reparse_file(repository_id, new_path, full_file_path)
        else:
            # File not found, treat as new file
            await self._reparse_file(repository_id, new_path, full_file_path)
    
    async def _create_file_record(
        self,
        repository_id: int,
        file_path: str,
        full_file_path: Path
    ) -> File:
        """Create a new file record."""
        # Determine language
        language = self._detect_language(full_file_path)
        
        # Calculate content hash for module summary optimization
        try:
            content = full_file_path.read_text(errors='ignore')
            line_count = len(content.splitlines())
            content_hash = hashlib.sha256(content.encode('utf-8', errors='ignore')).hexdigest()
        except Exception as e:
            logger.warning("file_read_failed", file_path=str(full_file_path), error=str(e))
            line_count = 0
            content_hash = ""
        
        file_record = File(
            repository_id=repository_id,
            path=file_path,
            language=language,
            symbol_count=0,
            line_count=line_count,
            content_hash=content_hash
        )
        
        self.session.add(file_record)
        await self.session.commit()
        await self.session.refresh(file_record)
        
        return file_record
    
    def _detect_language(self, file_path: Path) -> LanguageEnum:
        """Detect language from file extension."""
        suffix = file_path.suffix.lower()
        
        if suffix == '.cs':
            return LanguageEnum.CSHARP
        elif suffix in ['.js', '.jsx', '.mjs']:
            return LanguageEnum.JAVASCRIPT
        elif suffix in ['.ts', '.tsx']:
            return LanguageEnum.TYPESCRIPT
        elif suffix == '.vue':
            return LanguageEnum.VUE
        elif suffix == '.py':
            return LanguageEnum.PYTHON
        elif suffix in ['.md', '.markdown']:
            return LanguageEnum.MARKDOWN
        elif suffix in ['.sql', '.ddl']:
            return LanguageEnum.SQL
        elif suffix == '.csproj':
            return LanguageEnum.CSHARP  # .csproj files are C# project files
        elif suffix == '.sln':
            return LanguageEnum.CSHARP  # .sln files are C# solution files
        elif suffix == '.json':
            # Special handling for JSON files
            filename = file_path.name.lower()
            if filename.startswith('appsettings'):
                return LanguageEnum.CSHARP  # appsettings.json is C# config
            elif filename == 'package.json':
                return LanguageEnum.JAVASCRIPT  # package.json is npm/JavaScript
            return LanguageEnum.JAVASCRIPT  # Default for other JSON files
        else:
            return LanguageEnum.UNKNOWN
    
    async def rebuild_relationships_for_files(
        self,
        repository_id: int,
        file_ids: List[int]
    ):
        """
        Rebuild relationships for specific files.
        
        This is more efficient than rebuilding all relationships.
        
        Args:
            repository_id: Repository ID
            file_ids: List of file IDs that changed
        """
        logger.info(
            "rebuilding_relationships_for_files",
            repository_id=repository_id,
            file_count=len(file_ids)
        )
        
        # Get all symbols in these files
        result = await self.session.execute(
            select(Symbol).where(Symbol.file_id.in_(file_ids))
        )
        affected_symbols = result.scalars().all()
        affected_symbol_ids = [s.id for s in affected_symbols]
        
        # Delete existing relationships involving these symbols
        await self.session.execute(
            delete(Relation).where(
                (Relation.from_symbol_id.in_(affected_symbol_ids)) |
                (Relation.to_symbol_id.in_(affected_symbol_ids))
            )
        )
        await self.session.commit()
        
        # Rebuild relationships
        relationship_builder = RelationshipBuilder(self.session)
        await relationship_builder.build_relationships(repository_id)
        
        logger.info(
            "relationships_rebuilt",
            repository_id=repository_id,
            affected_symbols=len(affected_symbol_ids)
        )

