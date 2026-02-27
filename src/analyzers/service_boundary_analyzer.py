import logging
from typing import List, Dict, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, cast, String
from src.database.models import Repository, Service, Project, Symbol
from src.config.enums import SymbolKindEnum
from src.utils.async_compat import maybe_await

logger = logging.getLogger(__name__)

class ServiceBoundaryAnalyzer:
    """
    Detects service boundaries within a repository using C# specific heuristics.
    Follows the "Controller-First" strategy:
    1. Primary Signal: Presence of Controllers or Minimal API endpoints.
    2. Structural Signal: Project SDK (Web) and OutputType (Exe).
    3. Naming Signal: Project name suffixes (*.Service, *.API).
    """

    async def detect_services(self, repository: Repository, session: AsyncSession) -> List[Service]:
        """
        Scans the repository's projects to identify services.
        """
        detected_services = []
        
        # We need projects to be populated first. 
        # Assuming knowledge_extractor calls this AFTER project extraction.
        result = await session.execute(
            select(Project).filter(Project.repository_id == repository.id)
        )
        projects = result.scalars().all()
        
        logger.info(f"Service detection starting: found {len(projects)} projects to analyze")
        
        for project in projects:
            logger.info(f"Analyzing project: {project.name} (output_type={project.output_type})")
            score = 0
            is_service = False
            detection_reasons = []

            # 1. Structural Signal: SDK and OutputType
            # Note: We need to parse the .csproj file content or rely on Project fields if populated
            # For now, we'll assume we might need to re-read the file if Project model doesn't have raw XML data
            # But let's use what we have in the Project model or file path.
            
            # Heuristic: Web SDK
            # Since Project model doesn't store SDK directly yet, we might need to check file content
            # Or assume 'project_type' might capture it if enriched.
            # For this implementation, we will read the file content if possible or rely on project_type.
            
            # Let's try to read the file content to be sure
            try:
                import asyncio
                from pathlib import Path
                
                project_path = Path(project.file_path)
                
                # Check existence with timeout
                exists = await asyncio.wait_for(
                    asyncio.to_thread(project_path.exists),
                    timeout=1.0
                )
                
                if exists:
                    # Read content with timeout
                    content = await asyncio.wait_for(
                        asyncio.to_thread(project_path.read_text, encoding='utf-8'),
                        timeout=5.0
                    )
                        
                    if 'Sdk="Microsoft.NET.Sdk.Web"' in content:
                        score += 50
                        detection_reasons.append("Web SDK detected")

                    if 'Sdk="Microsoft.NET.Sdk.Worker"' in content:
                        score += 50
                        detection_reasons.append("Worker SDK detected")
                    
                    if '<OutputType>Exe</OutputType>' in content or 'Sdk="Microsoft.NET.Sdk.Web"' in content or 'Sdk="Microsoft.NET.Sdk.Worker"' in content:
                        score += 20
                        detection_reasons.append("Executable OutputType detected")
                        
                    if 'Microsoft.AspNetCore' in content:
                        score += 20
                        detection_reasons.append("ASP.NET Core dependency detected")
            except asyncio.TimeoutError:
                logger.warning(f"Timeout reading project file {project.file_path}")
            except Exception as e:
                logger.warning(f"Could not read project file {project.file_path}: {e}")

            # 2. Primary Signal: Controllers (The "Controller-First" check)
            # We look for Symbols in this project that are Controllers
            # Note: We cast attributes (JSON) to String to allow for text search
            result = await session.execute(
                select(Symbol).filter(
                    Symbol.project_id == project.id,
                    Symbol.kind == SymbolKindEnum.CLASS,
                    (Symbol.name.like("%Controller")) | 
                    (cast(Symbol.attributes, String).like("%ApiController%")) |
                    (cast(Symbol.attributes, String).like("%Route%"))
                )
            )
            controller_symbols = result.scalars().all()
            
            # Extract controller info for entry_points
            controllers_info = []
            if controller_symbols:
                score += 100
                is_service = True
                detection_reasons.append(f"Found {len(controller_symbols)} Controllers")
                
                # Build entry points list
                for ctrl in controller_symbols:
                    controllers_info.append({
                        "type": "controller",
                        "name": ctrl.name,
                        "fully_qualified_name": ctrl.fully_qualified_name
                    })

            # 3. Composition Root Signal (DI & CQRS)
            # A project that configures DI (AddScoped, AddTransient) or CQRS (AddMediatR) is likely a Service Host.
            try:
                project_path_obj = Path(project.file_path)
                
                # Check project exists with timeout
                project_exists = await asyncio.wait_for(
                    asyncio.to_thread(project_path_obj.exists),
                    timeout=1.0
                )
                
                if project_exists:
                    # We need to look at Program.cs or Startup.cs specifically
                    # Since we don't have a direct link to "Startup.cs" in Project model, we look for files in the project dir
                    project_dir = project_path_obj.parent
                    startup_files = ["Program.cs", "Startup.cs"]
                    
                    for startup_file in startup_files:
                        full_path = project_dir / startup_file
                        
                        # Check startup file exists with timeout
                        startup_exists = False
                        try:
                            startup_exists = await asyncio.wait_for(
                                asyncio.to_thread(full_path.exists),
                                timeout=0.5
                            )
                        except asyncio.TimeoutError:
                            continue
                            
                        if startup_exists:
                            try:
                                startup_content = await asyncio.wait_for(
                                    asyncio.to_thread(full_path.read_text, encoding='utf-8'),
                                    timeout=2.0
                                )
                                    
                                # Check for DI Container configuration
                                if "services.Add" in startup_content or "builder.Services.Add" in startup_content:
                                    score += 50
                                    detection_reasons.append("DI Container Configuration detected")
                                    
                                # Check for CQRS (MediatR)
                                if "AddMediatR" in startup_content:
                                    score += 30
                                    detection_reasons.append("CQRS (MediatR) detected")
                                    
                                # Check for MassTransit/Messaging
                                if "AddMassTransit" in startup_content or "AddNServiceBus" in startup_content:
                                    score += 30
                                    detection_reasons.append("Message Bus detected")
                                    
                                # Check for Host Builder (Strongest Signal for Worker/API)
                                if "CreateBuilder" in startup_content or "CreateDefaultBuilder" in startup_content or "CreateApplicationBuilder" in startup_content:
                                    score += 100
                                    is_service = True
                                    detection_reasons.append("Host Builder detected")
                            except asyncio.TimeoutError:
                                logger.warning(f"Timeout reading startup file {full_path}")
                                
            except Exception as e:
                logger.warning(f"Failed to analyze startup files for project {project.name}: {e}")

            # Deduplicate reasons
            detection_reasons = list(set(detection_reasons))

            # 4. Naming Signal (Tie-breaker)
            if project.name.endswith(".API") or project.name.endswith(".Service") or project.name.endswith(".Web"):
                score += 10
                detection_reasons.append("Naming convention match")

            # Decision Threshold
            if is_service or score >= 50:
                logger.info(f"✅ Detected Service: {project.name} (Score: {score}, Reasons: {detection_reasons})")
                logger.debug(f"   Taking API/Worker/Console detection path (score >= 50)")
                
                # Determine service type using multiple signals
                service_type = "Worker"  # Default
                
                if controller_symbols:
                    # Has controllers = API
                    service_type = "API"
                elif "Web SDK detected" in detection_reasons or "ASP.NET Core dependency detected" in detection_reasons:
                    # Has web SDK but no controllers (yet) - likely API that we'll confirm later
                    # Check the name for hints
                    if any(suffix in project.name for suffix in [".API", ".Api", ".WebApi"]):
                        service_type = "API"
                    else:
                        # Could be a web worker or background service
                        service_type = "Worker"
                elif "Console" in project.name or "Cli" in project.name:
                    service_type = "Console"
            else:
                # Try library detection (isolated method - minimal impact)
                logger.info(f"   Score < 50 ({score}), trying library detection for {project.name}")
                library_result = await self._detect_library_service(project, session)
                
                if library_result:
                    is_service, lib_score, lib_reasons, lib_service_type = library_result
                    score += lib_score
                    detection_reasons.extend(lib_reasons)
                    service_type = lib_service_type
                    logger.info(f"✅ Detected Library Service: {project.name} (Score: {score}, Reasons: {detection_reasons})")
                else:
                    logger.info(f"   Library detection returned None for {project.name}")
            
            # If not a service after all checks, skip
            if not is_service and score < 50:
                logger.info(f"❌ Skipping {project.name}: not a service (score={score})")
                continue
                
            # Check if service already exists (upsert logic)
            existing_service_result = await session.execute(
                select(Service).filter(
                    Service.repository_id == repository.id,
                    Service.name == project.name
                )
            )
            existing_service = existing_service_result.scalar_one_or_none()
            
            service_obj = None
            if existing_service:
                # Update existing service
                existing_service.service_type = service_type
                existing_service.description = f"Detected C# Service. Reasons: {', '.join(detection_reasons)}"
                existing_service.root_namespace = project.root_namespace
                existing_service.project_path = project.file_path
                existing_service.framework_version = project.target_framework
                existing_service.entry_points = controllers_info if controllers_info else None
                service_obj = existing_service
                logger.info(f"Updated existing service: {project.name}")
            else:
                # Create new service
                service_obj = Service(
                    repository_id=repository.id,
                    name=project.name,
                    service_type=service_type,
                    description=f"Detected C# Service. Reasons: {', '.join(detection_reasons)}",
                    root_namespace=project.root_namespace,
                    project_path=project.file_path,
                    framework_version=project.target_framework,
                    entry_points=controllers_info if controllers_info else None
                )
                await maybe_await(session.add(service_obj))
                logger.info(f"Created new service: {project.name}")
                
                # Flush to get service ID for new services
                await session.flush()
            
            # Count both new and updated services
            detected_services.append(service_obj)
            
            # Link symbols to this service
            # Update all symbols belonging to this project to have this service_id
            from sqlalchemy import update
            await session.execute(
                update(Symbol)
                .where(Symbol.project_id == project.id)
                .values(service_id=service_obj.id)
            )
            logger.debug(f"Linked symbols for project {project.name} to service {service_obj.id}")

        return detected_services

    async def _detect_library_service(
        self,
        project: Project,
        session: AsyncSession
    ) -> Optional[tuple[bool, int, List[str], str]]:
        """
        Detect if a project should be treated as a Library service.
        
        This method is isolated from main detection logic to minimize
        side effects. It checks if a class library has enough symbols
        to be meaningful for hierarchical exploration.
        
        Returns:
            Tuple of (is_service, score, reasons, service_type) or None if not a library
        """
        import asyncio
        from sqlalchemy import func
        from src.config.settings import get_settings
        
        # Feature flag check - allows instant disable
        if not get_settings().detect_library_services:
            logger.info(f"   Library detection disabled (DETECT_LIBRARY_SERVICES=false)")
            return None
        
        # Only process class libraries
        if not project.output_type or project.output_type.lower() != "library":
            logger.info(f"   Not a library (output_type={project.output_type})")
            return None
        
        try:
            # Count symbols with timeout to prevent slow queries
            symbol_count_result = await asyncio.wait_for(
                session.execute(
                    select(func.count(Symbol.id)).filter(
                        Symbol.project_id == project.id
                    )
                ),
                timeout=2.0  # 2 second hard limit
            )
            symbol_count = symbol_count_result.scalar() or 0
            
            # Check quality threshold
            if symbol_count < get_settings().min_library_symbols:
                logger.info(
                    f"   Library {project.name} has only {symbol_count} symbols "
                    f"(threshold: {get_settings().min_library_symbols}) - SKIPPED"
                )
                return None
            
            logger.info(f"   Library {project.name}: {symbol_count} symbols (threshold met)")
            
            # Build detection info
            is_service = True
            score = 10 + (symbol_count // 10)  # Small bonus for larger libraries
            reasons = [f"Class library with {symbol_count} symbols"]
            service_type = "Library"
            
            # Categorize by layer (defensive - handle any naming convention)
            name_lower = project.name.lower()
            if "domain" in name_lower:
                reasons.append("Domain layer detected")
            elif "application" in name_lower:
                reasons.append("Application layer detected")
            elif "infrastructure" in name_lower or "persistence" in name_lower:
                reasons.append("Infrastructure layer detected")
            elif "shared" in name_lower or "common" in name_lower:
                reasons.append("Shared library detected")
            elif "core" in name_lower:
                reasons.append("Core library detected")
            
            logger.info(f"Library service detected: {project.name} (score: {score}, {len(reasons)} reasons)")
            return (is_service, score, reasons, service_type)
            
        except asyncio.TimeoutError:
            logger.warning(f"Library detection timeout for {project.name} - query took >2s")
            return None
        except Exception as e:
            logger.error(f"Library detection error for {project.name}: {e}")
            return None
