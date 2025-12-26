"""
EF Core Entity Mapping Tools

MCP tools for retrieving Entity Framework Core entity mappings.
"""
from typing import List, Any
from mcp.types import TextContent
import json
from sqlalchemy import select
from src.database.session import get_async_session
from src.database.models import EfEntity, Repository
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


async def get_db_entity_mapping(repository_id: int, entity_name: str) -> List[TextContent]:
    """
    Get database entity mapping for a specific EF Core entity.
    
    Args:
        repository_id: Repository ID
        entity_name: Entity class name (e.g., "Order")
        
    Returns:
        List of TextContent with entity mapping or error
    """
    try:
        async with get_async_session() as session:
            # Query for the entity
            stmt = select(EfEntity).where(
                EfEntity.repository_id == repository_id,
                EfEntity.entity_name == entity_name
            )
            result = await session.execute(stmt)
            entity = result.scalar_one_or_none()
            
            if not entity:
                return [TextContent(
                    type="text",
                    text=f"Entity '{entity_name}' not found in repository {repository_id}"
                )]
            
            # Format response
            output = [f"# Entity Mapping: {entity.entity_name}\n"]
            output.append(f"**Repository**: {repository_id}")
            output.append(f"**Namespace**: {entity.namespace}")
            output.append(f"**Table Name**: {entity.table_name}")
            output.append(f"**Schema**: {entity.schema_name or 'dbo'}")
            
            if entity.primary_keys:
                output.append(f"\n## Primary Keys")
                for pk in entity.primary_keys:
                    output.append(f"- {pk}")
            
            if entity.properties:
                output.append(f"\n## Properties ({len(entity.properties)} total)")
                for prop in entity.properties[:20]:  # Show first 20
                    prop_name = prop.get("name", "Unknown")
                    prop_type = prop.get("type", "Unknown")
                    output.append(f"- **{prop_name}**: {prop_type}")
                if len(entity.properties) > 20:
                    output.append(f"... and {len(entity.properties) - 20} more properties")
            
            if entity.relationships:
                output.append(f"\n## Relationships ({len(entity.relationships)} total)")
                for rel in entity.relationships[:10]:  # Show first 10
                    rel_type = rel.get("type", "Unknown")
                    rel_target = rel.get("target", "Unknown")
                    output.append(f"- **{rel_type}**: {rel_target}")
                if len(entity.relationships) > 10:
                    output.append(f"... and {len(entity.relationships) - 10} more relationships")
            
            if entity.raw_mapping:
                output.append(f"\n## Raw Mapping")
                output.append("```json")
                output.append(json.dumps(entity.raw_mapping, indent=2))
                output.append("```")
            
            return [TextContent(type="text", text="\n".join(output))]
            
    except Exception as e:
        logger.error(
            "get_db_entity_mapping_failed",
            repository_id=repository_id,
            entity_name=entity_name,
            error=str(e),
            error_type=type(e).__name__
        )
        return [TextContent(
            type="text",
            text=f"Failed to retrieve entity mapping: {str(e)}"
        )]


async def list_ef_entities(repository_id: int, limit: int = 50) -> List[TextContent]:
    """
    List all EF Core entities in a repository.
    
    Args:
        repository_id: Repository ID
        limit: Maximum number of entities to return
        
    Returns:
        List of TextContent with entities or error
    """
    try:
        async with get_async_session() as session:
            # Get repository info
            repo_stmt = select(Repository).where(Repository.id == repository_id)
            repo_result = await session.execute(repo_stmt)
            repository = repo_result.scalar_one_or_none()
            
            if not repository:
                return [TextContent(
                    type="text",
                    text=f"Repository {repository_id} not found"
                )]
            
            # Query entities
            stmt = select(EfEntity).where(
                EfEntity.repository_id == repository_id
            ).limit(limit)
            result = await session.execute(stmt)
            entities = result.scalars().all()
            
            if not entities:
                return [TextContent(
                    type="text",
                    text=f"No EF Core entities found in repository {repository_id} ({repository.name})"
                )]
            
            # Format response
            output = [f"# EF Core Entities in {repository.name}\n"]
            output.append(f"**Repository ID**: {repository_id}")
            output.append(f"**Total Entities**: {len(entities)}\n")
            
            for entity in entities:
                output.append(f"## {entity.entity_name}")
                output.append(f"- **Namespace**: {entity.namespace}")
                output.append(f"- **Table**: {entity.schema_name or 'dbo'}.{entity.table_name}")
                if entity.primary_keys:
                    output.append(f"- **Primary Keys**: {', '.join(entity.primary_keys)}")
                output.append(f"- **Properties**: {len(entity.properties or [])}")
                output.append(f"- **Relationships**: {len(entity.relationships or [])}")
                output.append("")
            
            return [TextContent(type="text", text="\n".join(output))]
            
    except Exception as e:
        logger.error(
            "list_ef_entities_failed",
            repository_id=repository_id,
            error=str(e),
            error_type=type(e).__name__
        )
        return [TextContent(
            type="text",
            text=f"Failed to list entities: {str(e)}"
        )]
