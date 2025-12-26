"""
Helper functions for worker tasks.
"""

import hashlib
from src.database.session import engine
from src.database.models import Symbol, File
from sqlalchemy import select, func

async def _run_with_engine_cleanup(coro):
    """
    Run an async coroutine and ensure proper engine cleanup.
    
    This helper ensures that database connections are properly disposed
    after each async operation to prevent "another operation is in progress" errors.
    """
    try:
        return await coro
    finally:
        # Dispose of all connections in the pool for this event loop
        # This prevents connection reuse issues across asyncio.run() calls
        await engine.dispose()


def _calculate_content_hash(content: str) -> str:
    """
    Calculate a stable content hash for file content.
    
    Normalizes line endings to ensure consistent hashing across platforms.
    
    Args:
        content: File content string
        
    Returns:
        SHA256 hash of normalized content
    """
    # Normalize line endings to LF for consistent hashing
    normalized_content = content.replace('\r\n', '\n').replace('\r', '\n')
    return hashlib.sha256(normalized_content.encode('utf-8', errors='ignore')).hexdigest()


async def _count_symbols(session, repository_id: int) -> int:
    """Count total symbols in repository."""
    result = await session.execute(
        select(func.count(Symbol.id))
        .join(File)
        .where(File.repository_id == repository_id)
    )
    count = result.scalar()
    return count or 0
