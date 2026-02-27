"""Database connection pooling for improved performance."""

from typing import Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import AsyncAdaptedQueuePool
from src.config.settings import get_settings
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class DatabaseConnectionPool:
    """Manages database connection pool."""
    
    def __init__(self):
        """Initialize connection pool."""
        self._engine: Optional[AsyncEngine] = None
        self._session_maker: Optional[async_sessionmaker] = None
        self._initialized = False
    
    async def initialize(self):
        """
        Initialize the connection pool with optimized get_settings().
        """
        if self._initialized:
            return
        
        settings = get_settings()
        
        # Create engine with connection pooling
        self._engine = create_async_engine(
            get_settings().database_url,
            poolclass=AsyncAdaptedQueuePool,
            pool_size=20,  # Number of connections to maintain
            max_overflow=10,  # Additional connections if pool is full
            pool_pre_ping=True,  # Verify connections before using
            pool_recycle=3600,  # Recycle connections after 1 hour
            echo=False,  # Set to True for SQL query logging
            # Performance optimizations
            connect_args={
                "server_settings": {
                    "jit": "off",  # Disable JIT for better connection speed
                },
                "command_timeout": 60,  # 60 second query timeout
                "prepared_statement_cache_size": 500,  # Cache prepared statements
            }
        )
        
        # Create session maker
        self._session_maker = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,  # Don't expire objects after commit
            autoflush=False,  # Manual flush control
            autocommit=False
        )
        
        self._initialized = True
        logger.info(
            "connection_pool_initialized",
            pool_size=20,
            max_overflow=10
        )
    
    async def get_session(self) -> AsyncSession:
        """
        Get a database session from the pool.
        
        Returns:
            AsyncSession instance
        """
        if not self._initialized:
            await self.initialize()
        
        return self._session_maker()
    
    async def dispose(self):
        """Dispose of the connection pool."""
        if self._engine:
            await self._engine.dispose()
            self._initialized = False
            logger.info("connection_pool_disposed")
    
    async def health_check(self) -> bool:
        """
        Check if database connection is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            session = await self.get_session()
            async with session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error("health_check_failed", error=str(e))
            return False
    
    async def get_pool_status(self) -> dict:
        """
        Get current pool status.
        
        Returns:
            Dict with pool statistics
        """
        if not self._engine:
            return {"status": "not_initialized"}
        
        pool = self._engine.pool
        
        return {
            "status": "healthy" if await self.health_check() else "unhealthy",
            "size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "total_connections": pool.size() + pool.overflow()
        }


# Global connection pool instance
_connection_pool: Optional[DatabaseConnectionPool] = None


async def get_connection_pool() -> DatabaseConnectionPool:
    """Get or create global connection pool."""
    global _connection_pool
    
    if _connection_pool is None:
        _connection_pool = DatabaseConnectionPool()
        await _connection_pool.initialize()
    
    return _connection_pool


async def get_db_session() -> AsyncSession:
    """
    Get database session from pool.
    
    Usage:
        async with get_db_session() as session:
            # Use session
            pass
    """
    pool = await get_connection_pool()
    return await pool.get_session()

