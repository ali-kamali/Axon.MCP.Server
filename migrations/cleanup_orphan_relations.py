"""
Cleanup orphan relations - Remove relations pointing to non-existent symbols.

This migration cleans up existing foreign key violations by deleting relations
where the to_symbol_id references a symbol that doesn't exist in the symbols table.
"""

from sqlalchemy import text
from src.database.session import AsyncSessionLocal
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


async def migrate():
    """Remove orphan relations from database."""
    logger.info("cleanup_orphan_relations_started")
    
    async with AsyncSessionLocal() as session:
        try:
            # Find and delete orphan relations
            delete_query = text("""
                DELETE FROM relations
                WHERE id IN (
                    SELECT r.id 
                    FROM relations r
                    LEFT JOIN symbols s ON r.to_symbol_id = s.id
                    WHERE s.id IS NULL
                )
            """)
            
            result = await session.execute(delete_query)
            deleted_count = result.rowcount
            
            await session.commit()
            
            logger.info(
                "cleanup_orphan_relations_completed",
                deleted_count=deleted_count
            )
            
            return deleted_count
            
        except Exception as e:
            await session.rollback()
            logger.error(
                "cleanup_orphan_relations_failed",
                error=str(e)
            )
            raise


async def rollback():
    """No rollback needed - orphan relations should be removed."""
    logger.info("cleanup_orphan_relations_rollback_skipped")
    pass


if __name__ == "__main__":
    import asyncio
    asyncio.run(migrate())
