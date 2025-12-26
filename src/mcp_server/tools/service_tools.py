from typing import List, Dict, Any, Optional
from mcp.types import TextContent
from sqlalchemy import select, String
from sqlalchemy.orm import selectinload

from src.database.session import get_async_session
from src.database.models import Service, Symbol, Repository
from src.config.enums import SymbolKindEnum
from src.generators.service_doc_generator import ServiceDocGenerator
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

async def list_services(repository_id: Optional[int] = None) -> List[TextContent]:
    """
    List detected services in the codebase.
    
    Args:
        repository_id: Optional repository ID to filter by
        
    Returns:
        List of services with basic info
    """
    async with get_async_session() as session:
        query = select(Service)
        if repository_id:
            query = query.where(Service.repository_id == repository_id)
            
        result = await session.execute(query)
        services = result.scalars().all()
        
        if not services:
            return [TextContent(type="text", text="No services detected.")]
            
        output = ["Detected Services:"]
        for service in services:
            output.append(f"- {service.name} ({service.service_type})")
            output.append(f"  Path: {service.project_path}")
            if service.description:
                output.append(f"  Description: {service.description}")
            output.append("")
            
        return [TextContent(type="text", text="\n".join(output))]

async def get_service_details(service_name: str) -> List[TextContent]:
    """
    Get detailed information about a specific service.
    
    Args:
        service_name: Name of the service
        
    Returns:
        Detailed service information including controllers and dependencies
    """
    async with get_async_session() as session:
        # Find service by name
        query = select(Service).where(Service.name == service_name)
        result = await session.execute(query)
        service = result.scalar_one_or_none()
        
        if not service:
            return [TextContent(type="text", text=f"Service '{service_name}' not found.")]
            
        # Get controllers
        controllers_query = select(Symbol).where(
            Symbol.service_id == service.id,
            Symbol.kind == SymbolKindEnum.CLASS,
            (Symbol.name.like("%Controller")) | (Symbol.attributes.cast(String).contains("ApiController"))
        )
        result = await session.execute(controllers_query)
        controllers = result.scalars().all()
        
        output = [f"Service: {service.name}"]
        output.append(f"Type: {service.service_type}")
        output.append(f"Framework: {service.framework_version}")
        output.append(f"Root Namespace: {service.root_namespace}")
        output.append(f"Project Path: {service.project_path}")
        output.append("")
        
        if controllers:
            output.append("Controllers:")
            for controller in controllers:
                output.append(f"- {controller.name}")
        else:
            output.append("No controllers detected.")
            
        return [TextContent(type="text", text="\n".join(output))]

async def get_service_documentation(service_name: str) -> List[TextContent]:
    """
    Get comprehensive markdown documentation for a service.
    
    Args:
        service_name: Name of the service
        
    Returns:
        Markdown documentation
    """
    async with get_async_session() as session:
        # Find service
        query = select(Service).where(Service.name == service_name)
        result = await session.execute(query)
        service = result.scalar_one_or_none()
        
        if not service:
            return [TextContent(type="text", text=f"Service '{service_name}' not found.")]
            
        # Generate documentation
        generator = ServiceDocGenerator(session)
        doc = await generator.generate_service_doc(service)
        
        return [TextContent(type="text", text=doc)]
