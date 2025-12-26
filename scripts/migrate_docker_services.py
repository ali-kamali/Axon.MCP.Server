"""Migration script to add Docker service tables.

This script adds:
- docker_services table
- service_repository_mappings table
"""

import asyncio
from sqlalchemy import text
from src.database.connection import get_async_session
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


async def migrate_docker_services():
    """Add Docker service tables to the database."""
    
    async for session in get_async_session():
        try:
            logger.info("migration_starting", migration="docker_services")
            
            # Create docker_services table
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS docker_services (
                    id SERIAL PRIMARY KEY,
                    repository_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
                    file_path VARCHAR(1000) NOT NULL,
                    
                    service_name VARCHAR(255) NOT NULL,
                    image VARCHAR(500),
                    container_name VARCHAR(255),
                    
                    build_context VARCHAR(1000),
                    dockerfile VARCHAR(500),
                    build_args JSONB,
                    
                    ports JSONB,
                    expose JSONB,
                    networks JSONB,
                    
                    depends_on JSONB,
                    links JSONB,
                    
                    environment JSONB,
                    volumes JSONB,
                    
                    command TEXT,
                    entrypoint TEXT,
                    working_dir VARCHAR(1000),
                    user VARCHAR(100),
                    restart VARCHAR(50),
                    
                    healthcheck JSONB,
                    labels JSONB,
                    
                    service_metadata JSONB,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    
                    CONSTRAINT uq_docker_service_repo_file_name UNIQUE (repository_id, file_path, service_name)
                )
            """))
            
            # Create indexes for docker_services
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_docker_service_repo ON docker_services(repository_id)
            """))
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_docker_service_name ON docker_services(service_name)
            """))
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_docker_service_image ON docker_services(image)
            """))
            
            logger.info("migration_table_created", table="docker_services")
            
            # Create service_repository_mappings table
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS service_repository_mappings (
                    id SERIAL PRIMARY KEY,
                    
                    docker_service_id INTEGER REFERENCES docker_services(id) ON DELETE CASCADE,
                    service_name VARCHAR(255) NOT NULL,
                    
                    target_repository_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
                    
                    confidence INTEGER NOT NULL,
                    mapping_method VARCHAR(50) NOT NULL,
                    mapping_metadata JSONB,
                    
                    is_manual INTEGER DEFAULT 0,
                    
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    
                    CONSTRAINT uq_service_mapping_service_repo UNIQUE (docker_service_id, target_repository_id)
                )
            """))
            
            # Create indexes for service_repository_mappings
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_service_mapping_docker_service ON service_repository_mappings(docker_service_id)
            """))
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_service_mapping_target_repo ON service_repository_mappings(target_repository_id)
            """))
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_service_mapping_service_name ON service_repository_mappings(service_name)
            """))
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_service_mapping_confidence ON service_repository_mappings(confidence)
            """))
            
            logger.info("migration_table_created", table="service_repository_mappings")
            
            await session.commit()
            logger.info("migration_completed", migration="docker_services")
            
        except Exception as e:
            await session.rollback()
            logger.error("migration_failed", migration="docker_services", error=str(e))
            raise
        finally:
            await session.close()
            break


if __name__ == "__main__":
    asyncio.run(migrate_docker_services())
