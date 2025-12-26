"""Link Service for connecting API calls to endpoints and events to subscribers.

This service implements the core logic for Phase 3: The Linker.
It provides:
1. Gateway resolution (Ocelot/Nginx) to map frontend paths to backend paths
2. Fuzzy URL matching to connect outgoing API calls to backend endpoints
3. Event linking to connect publishers to subscribers across repositories
"""

import re
from typing import List, Dict, Any, Optional, Tuple, Set
from difflib import SequenceMatcher
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, or_, select, func, delete
from sqlalchemy.future import select as future_select
import warnings
import structlog

from src.database.models import (
    OutgoingApiCall,
    Symbol,
    PublishedEvent,
    EventSubscription,
    ApiEndpointLink,
    EventLink,
    GatewayRoute,
    Repository,
    File,
)
from src.config.enums import SymbolKindEnum
from src.parsers.ocelot_parser import OcelotParser
from src.parsers.nginx_parser import NginxParser

logger = structlog.get_logger(__name__)


class LinkService:
    """Service for creating links between API calls, endpoints, and events.
    
    This service is the core of Phase 3: The Linker. It connects:
    - Frontend API calls → Backend endpoints (via fuzzy matching and gateway resolution)
    - Event publishers → Event subscribers (via event type matching)
    """
    
    # Confidence thresholds for creating links (0-100)
    CONFIDENCE_THRESHOLD = 70  # 70% confidence minimum for API links
    EVENT_CONFIDENCE_THRESHOLD = 80  # 80% for event links
    
    def __init__(self, db: AsyncSession):
        """Initialize the link service with a database session.
        
        Args:
            db: AsyncSession for database operations
        """
        self.db = db
        self.ocelot_parser = OcelotParser()
        self.nginx_parser = NginxParser()
        self._gateway_routes_cache: Dict[int, List[GatewayRoute]] = {}
        self._endpoint_cache: Dict[str, List[Symbol]] = {}
    
    async def parse_all_gateway_configs(
        self,
        repository_ids: Optional[List[int]] = None
    ) -> List[GatewayRoute]:
        """
        Parse all gateway configuration files and store routes in database.
        
        Args:
            repository_ids: Optional list of repository IDs to process
            
        Returns:
            List of created GatewayRoute objects
        """
        # Build query for gateway config files
        query = select(File).where(
            or_(
                File.path.ilike('%ocelot%.json'),
                File.path.ilike('%.conf'),
                File.path.ilike('%nginx%')
            )
        )
        
        if repository_ids:
            query = query.where(File.repository_id.in_(repository_ids))
        
        result = await self.db.execute(query)
        gateway_files = result.scalars().all()
        
        created_routes = []
        
        for file in gateway_files:
            try:
                # Get repository to construct file path
                repo_result = await self.db.execute(
                    select(Repository).where(Repository.id == file.repository_id)
                )
                repo = repo_result.scalar_one_or_none()
                if not repo:
                    continue
                
                # Read file content from cloned repository
                content = await self._read_file_content(file, repo)
                if not content:
                    continue
                
                routes = []
                gateway_type = None
                
                if self.ocelot_parser.is_ocelot_config(file.path):
                    gateway_type = 'ocelot'
                    routes = self.ocelot_parser.parse_ocelot_config(file.path, content)
                elif self.nginx_parser.is_nginx_config(file.path):
                    gateway_type = 'nginx'
                    routes = self.nginx_parser.parse_nginx_config(file.path, content)
                else:
                    continue
                
                # [FIX] Delete existing routes for this file before adding new ones
                # This prevents duplicate routes accumulating on every sync
                await self.db.execute(
                    delete(GatewayRoute).where(
                        GatewayRoute.repository_id == file.repository_id,
                        GatewayRoute.file_path == file.path
                    )
                )
                
                # Store routes in database
                for route_data in routes:
                    gateway_route = GatewayRoute(
                        repository_id=file.repository_id,
                        file_path=file.path,
                        gateway_type=gateway_type,
                        downstream_path_template=route_data.get('downstream_path'),
                        upstream_path_template=route_data.get('upstream_path'),
                        upstream_host=route_data.get('upstream_host'),
                        upstream_port=route_data.get('upstream_port'),
                        http_methods=route_data.get('http_methods'),
                        route_name=route_data.get('route_name'),
                        priority=route_data.get('priority', 0),
                        route_metadata=route_data.get('metadata')
                    )
                    self.db.add(gateway_route)
                    created_routes.append(gateway_route)
                
                logger.info(
                    "gateway_config_parsed",
                    file_path=file.path,
                    repository_id=file.repository_id,
                    gateway_type=gateway_type,
                    routes_count=len(routes)
                )
                
            except Exception as e:
                logger.error(
                    "gateway_parse_failed",
                    file_path=file.path,
                    error=str(e)
                )
        
        if created_routes:
            await self.db.flush()
        
        return created_routes
    
    async def _read_file_content(self, file: File, repo: Repository) -> Optional[str]:
        """Read file content from the cloned repository."""
        from pathlib import Path
        from src.config.settings import settings
        from src.config.enums import SourceControlProviderEnum
        
        try:
            # Construct path based on provider
            if repo.provider == SourceControlProviderEnum.AZUREDEVOPS:
                repo_path = Path(settings.repo_cache_dir).resolve() / "azuredevops" / repo.azuredevops_project_name / repo.name
            else:
                repo_path = Path(settings.repo_cache_dir).resolve() / repo.path_with_namespace.replace("/", "_")
            
            file_path = repo_path / file.path
            
            if file_path.exists():
                return file_path.read_text(encoding='utf-8-sig', errors='ignore')
            
        except Exception as e:
            logger.warning("file_read_failed", file_path=file.path, error=str(e))
        
        return None
    
    async def link_api_calls_to_endpoints(
        self,
        repository_ids: Optional[List[int]] = None,
        gateway_routes: Optional[List[GatewayRoute]] = None
    ) -> int:
        """
        Link outgoing API calls to their target backend endpoints.
        
        This is the main method for Phase 3: The Linker. It:
        1. Fetches all outgoing API calls from specified repositories
        2. Loads gateway routes for URL resolution
        3. Finds candidate backend endpoints (API controllers/handlers)
        4. Uses fuzzy matching to link calls to endpoints
        5. Creates ApiEndpointLink records for matches above threshold
        
        Args:
            repository_ids: Optional list of repository IDs to process
            gateway_routes: Optional list of gateway routes for resolution
            
        Returns:
            Number of links created
        """
        # Fetch outgoing calls
        query = select(OutgoingApiCall)
        if repository_ids:
            query = query.where(OutgoingApiCall.repository_id.in_(repository_ids))
        
        result = await self.db.execute(query)
        outgoing_calls = result.scalars().all()
        
        if not outgoing_calls:
            logger.info("no_outgoing_calls_found")
            return 0
        
        # Load gateway routes if not provided
        if gateway_routes is None:
            routes_result = await self.db.execute(select(GatewayRoute))
            gateway_routes = routes_result.scalars().all()
        
        # Pre-load all backend endpoints for efficiency
        await self._preload_endpoints(repository_ids)
        
        links_created = 0
        
        for call in outgoing_calls:
            try:
                match = await self._find_matching_endpoint_async(call, gateway_routes)
                
                if match:
                    symbol, confidence, method, metadata = match
                    
                    # Check for existing link to avoid duplicates
                    existing = await self.db.execute(
                        select(ApiEndpointLink).where(
                            ApiEndpointLink.outgoing_call_id == call.id,
                            ApiEndpointLink.target_symbol_id == symbol.id
                        )
                    )
                    if existing.scalar_one_or_none():
                        continue
                    
                    # Create link
                    link = ApiEndpointLink(
                        outgoing_call_id=call.id,
                        source_repository_id=call.repository_id,
                        target_symbol_id=symbol.id,
                        target_repository_id=symbol.file.repository_id if symbol.file else None,
                        match_confidence=int(confidence * 100),
                        match_method=method,
                        match_metadata=metadata
                    )
                    
                    self.db.add(link)
                    links_created += 1
                    
                    if links_created % 100 == 0:
                        await self.db.flush()
                        logger.info("api_links_progress", links_created=links_created)
                
            except Exception as e:
                logger.error(
                    "api_link_failed",
                    call_id=call.id,
                    url=call.url_pattern,
                    error=str(e)
                )
        
        if links_created > 0:
            await self.db.flush()
        
        logger.info("api_linking_complete", total_links=links_created)
        return links_created
    
    async def _preload_endpoints(self, repository_ids: Optional[List[int]] = None) -> None:
        """Pre-load backend endpoints for efficient matching."""
        # Clear cache
        self._endpoint_cache.clear()
        
        # Find all endpoint symbols (controllers, route handlers)
        query = select(Symbol).join(File)
        
        # Filter by ENDPOINT kind or controller methods
        query = query.where(
            or_(
                Symbol.kind == SymbolKindEnum.ENDPOINT,
                and_(
                    Symbol.kind == SymbolKindEnum.METHOD,
                    Symbol.fully_qualified_name.ilike('%Controller.%')
                )
            )
        )
        
        if repository_ids:
            query = query.where(File.repository_id.in_(repository_ids))
        
        result = await self.db.execute(query)
        endpoints = result.scalars().all()
        
        # Index by normalized route pattern
        for endpoint in endpoints:
            route = self._extract_route_from_symbol(endpoint)
            if route:
                normalized = self._normalize_url_pattern(route)
                if normalized not in self._endpoint_cache:
                    self._endpoint_cache[normalized] = []
                self._endpoint_cache[normalized].append(endpoint)
        
        logger.info("endpoints_preloaded", count=len(endpoints), cache_keys=len(self._endpoint_cache))
    
    async def _find_matching_endpoint_async(
        self,
        outgoing_call: OutgoingApiCall,
        gateway_routes: List[GatewayRoute]
    ) -> Optional[Tuple[Symbol, float, str, Dict]]:
        """
        Find the best matching backend endpoint for an outgoing API call.
        
        This is the core matching algorithm that:
        1. Attempts gateway resolution to translate frontend paths
        2. Normalizes URL patterns for comparison
        3. Uses cache for fast candidate lookup
        4. Scores candidates using URL similarity, HTTP method, and context
        
        Returns:
            Tuple of (matched_symbol, confidence_score, match_method, metadata)
        """
        url_pattern = outgoing_call.url_pattern
        
        # Step 1: Try to resolve through gateway
        resolved_url, gateway_metadata = self._resolve_through_gateway(
            url_pattern,
            gateway_routes
        )
        
        effective_url = resolved_url or url_pattern
        
        # Step 2: Find candidate endpoints
        candidates = await self._find_candidate_endpoints_async(
            url_pattern=effective_url,
            http_method=outgoing_call.http_method
        )
        
        if not candidates:
            # Try with just the normalized pattern from cache
            normalized = self._normalize_url_pattern(effective_url)
            if normalized in self._endpoint_cache:
                candidates = self._endpoint_cache[normalized]
        
        # Step 3: Score each candidate
        best_match = None
        best_score = 0.0
        best_method = 'fuzzy'
        best_metadata = {}
        
        for candidate in candidates:
            score, metadata = self._calculate_match_score(
                outgoing_call,
                candidate,
                resolved_url
            )
            
            if score > best_score:
                best_score = score
                best_match = candidate
                best_metadata = metadata
                if resolved_url:
                    best_method = 'gateway_resolved'
                    best_metadata.update(gateway_metadata)
                elif score >= 0.9:
                    best_method = 'exact'
                else:
                    best_method = 'fuzzy'
        
        # Only return if confidence meets threshold
        threshold = self.CONFIDENCE_THRESHOLD / 100.0
        if best_match and best_score >= threshold:
            return (best_match, best_score, best_method, best_metadata)
        
        # Log near-misses for threshold tuning (scores between 50% and threshold)
        if best_match and 0.5 <= best_score < threshold:
            logger.info(
                "api_link_near_miss",
                url_pattern=outgoing_call.url_pattern,
                http_method=outgoing_call.http_method,
                candidate_name=best_match.name,
                score=round(best_score * 100, 1),
                threshold=self.CONFIDENCE_THRESHOLD,
                metadata=best_metadata
            )
        
        return None
    
    def find_matching_endpoint(
        self,
        outgoing_call: OutgoingApiCall,
        gateway_routes: List[GatewayRoute]
    ) -> Optional[Tuple[Symbol, float, str, Dict]]:
        """
        Synchronous wrapper for backwards compatibility.
        
        .. deprecated:: 1.0
            Use :meth:`_find_matching_endpoint_async` instead.
            This method cannot be called from async contexts and will return None.
        
        Note: For new code, use _find_matching_endpoint_async instead.
        """
        warnings.warn(
            "find_matching_endpoint is deprecated. Use _find_matching_endpoint_async instead.",
            DeprecationWarning,
            stacklevel=2
        )
        # This is a sync fallback - use async version in new code
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Can't run sync in async context, return None
                logger.warning("sync_wrapper_called_from_async_context")
                return None
            return loop.run_until_complete(
                self._find_matching_endpoint_async(outgoing_call, gateway_routes)
            )
        except RuntimeError:
            return None
    
    def _resolve_through_gateway(
        self,
        frontend_url: str,
        gateway_routes: List[GatewayRoute]
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        Resolve frontend URL through gateway routes to get backend URL.
        
        This handles the translation of frontend-facing URLs to backend-facing URLs
        through API gateways like Ocelot or Nginx.
        
        Args:
            frontend_url: The URL pattern from frontend code (e.g., '/api/users/123')
            gateway_routes: List of parsed gateway routes
            
        Returns:
            Tuple of (resolved_backend_url, gateway_metadata)
        """
        if not gateway_routes:
            return None, {}
        
        # Sort routes by priority (higher first)
        sorted_routes = sorted(
            gateway_routes, 
            key=lambda r: (r.priority or 0, -len(r.downstream_path_template or '')),
            reverse=True
        )
        
        for route in sorted_routes:
            downstream = route.downstream_path_template
            upstream = route.upstream_path_template
            
            if not downstream:
                continue
            
            # Try to match the frontend URL against the downstream (frontend-facing) template
            if route.gateway_type == 'ocelot':
                backend_url = self.ocelot_parser.resolve_path_through_route(
                    frontend_url,
                    {
                        'downstream_path': downstream,
                        'upstream_path': upstream
                    }
                )
            elif route.gateway_type == 'nginx':
                backend_url = self.nginx_parser.resolve_path_through_route(
                    frontend_url,
                    {
                        'downstream_path': downstream,
                        'upstream_path': upstream,
                        'is_regex': route.route_metadata.get('modifier', '').startswith('~') if route.route_metadata else False
                    }
                )
            else:
                continue
            
            if backend_url:
                metadata = {
                    'gateway_type': route.gateway_type,
                    'gateway_route_id': route.id,
                    'original_url': frontend_url,
                    'upstream_host': route.upstream_host,
                    'upstream_port': route.upstream_port,
                    'route_name': route.route_name
                }
                logger.debug(
                    "gateway_resolution_success",
                    frontend_url=frontend_url,
                    backend_url=backend_url,
                    gateway_type=route.gateway_type
                )
                return backend_url, metadata
        
        return None, {}
    
    async def _find_candidate_endpoints_async(
        self,
        url_pattern: str,
        http_method: str
    ) -> List[Symbol]:
        """
        Find candidate backend endpoints that might match the URL pattern.
        
        Uses multiple strategies:
        1. Direct cache lookup by normalized URL
        2. Partial match using URL segments
        3. Database query for controller methods
        
        Returns:
            List of Symbol objects representing API endpoints
        """
        candidates = []
        normalized_url = self._normalize_url_pattern(url_pattern)
        
        # Strategy 1: Direct cache lookup
        if normalized_url in self._endpoint_cache:
            candidates.extend(self._endpoint_cache[normalized_url])
        
        # Strategy 2: Partial match - look for endpoints with similar segments
        url_segments = set(normalized_url.split('/'))
        url_segments.discard('')
        url_segments.discard('*')
        url_segments.discard('api')  # Too common
        
        for cache_key, cache_endpoints in self._endpoint_cache.items():
            cache_segments = set(cache_key.split('/'))
            cache_segments.discard('')
            cache_segments.discard('*')
            cache_segments.discard('api')
            
            # If there's significant overlap, consider as candidate
            if len(url_segments & cache_segments) >= 1:
                for endpoint in cache_endpoints:
                    if endpoint not in candidates:
                        candidates.append(endpoint)
        
        # Strategy 3: Database query for additional candidates if cache is insufficient
        if len(candidates) < 20:
            # Look for symbols that are likely API endpoints
            query = select(Symbol).join(File).where(
                or_(
                    # Explicit endpoint symbols
                    Symbol.kind == SymbolKindEnum.ENDPOINT,
                    # C# Controller methods
                    and_(
                        Symbol.kind == SymbolKindEnum.METHOD,
                        Symbol.fully_qualified_name.ilike('%Controller.%')
                    ),
                    # Express/NestJS routes
                    and_(
                        Symbol.kind == SymbolKindEnum.FUNCTION,
                        or_(
                            Symbol.name.ilike('app.%'),
                            Symbol.name.ilike('router.%')
                        )
                    )
                )
            ).limit(500)
            
            result = await self.db.execute(query)
            db_candidates = result.scalars().all()
            
            for c in db_candidates:
                if c not in candidates:
                    candidates.append(c)
        
        return candidates[:200]  # Limit to prevent excessive processing
    
    def _find_candidate_endpoints(
        self,
        url_pattern: str,
        http_method: str
    ) -> List[Symbol]:
        """
        Synchronous wrapper for backwards compatibility.
        
        .. deprecated:: 1.0
            Use :meth:`_find_candidate_endpoints_async` instead.
            This method only returns cached results and cannot query the database.
        
        Note: This returns from cache only in sync context.
        """
        warnings.warn(
            "_find_candidate_endpoints is deprecated. Use _find_candidate_endpoints_async instead.",
            DeprecationWarning,
            stacklevel=2
        )
        normalized = self._normalize_url_pattern(url_pattern)
        candidates = []
        
        if normalized in self._endpoint_cache:
            candidates.extend(self._endpoint_cache[normalized])
        
        return candidates
    
    def _calculate_match_score(
        self,
        call: OutgoingApiCall,
        endpoint: Symbol,
        resolved_url: Optional[str]
    ) -> Tuple[float, Dict]:
        """
        Calculate confidence score for a potential match.
        
        Returns:
            Tuple of (score, metadata_dict)
        """
        score = 0.0
        metadata = {}
        
        # 1. URL pattern similarity (50% weight)
        url_to_match = resolved_url or call.url_pattern
        endpoint_route = self._extract_route_from_symbol(endpoint)
        
        if endpoint_route:
            if self._exact_match(url_to_match, endpoint_route):
                score += 0.5
                metadata['url_match'] = 'exact'
            else:
                # Fuzzy match using path similarity
                similarity = self._path_similarity(url_to_match, endpoint_route)
                score += 0.5 * similarity
                metadata['url_match'] = 'fuzzy'
                metadata['url_similarity'] = similarity
        
        # 2. HTTP method match (30% weight)
        if self._http_method_matches(call.http_method, endpoint):
            score += 0.3
            metadata['method_match'] = True
        else:
            metadata['method_match'] = False
        
        # 3. Context bonus (20% weight)
        if resolved_url:
            # Gateway resolution gives us high confidence
            score += 0.2
            metadata['gateway_resolved'] = True
        else:
            # Check if repositories are likely to communicate
            # (e.g., same organization, related services)
            score += 0.1  # Base bonus for now
            metadata['gateway_resolved'] = False
        
        return (score, metadata)
    
    def _extract_route_from_symbol(self, symbol: Symbol) -> Optional[str]:
        """Extract API route pattern from a symbol's structured_docs or attributes."""
        # Check structured_docs for route information
        if symbol.structured_docs:
            # API endpoint type
            if symbol.structured_docs.get('type') == 'api_endpoint':
                return symbol.structured_docs.get('route')
            
            # Express routes
            if 'express_route' in symbol.structured_docs:
                return symbol.structured_docs.get('express_route')
            
            # C# Route attributes in structured docs
            if 'route' in symbol.structured_docs:
                return symbol.structured_docs.get('route')
            
            # Extract from attributes array
            attributes = symbol.structured_docs.get('attributes', [])
            for attr in attributes:
                attr_name = attr.get('name', '')
                if attr_name in ['Route', 'HttpGet', 'HttpPost', 'HttpPut', 'HttpDelete', 'HttpPatch']:
                    args = attr.get('arguments', [])
                    if args:
                        return args[0].strip('"\'')
        
        # Also check the top-level attributes field
        if symbol.attributes:
            for attr in symbol.attributes:
                if isinstance(attr, dict):
                    attr_name = attr.get('name', '')
                    if attr_name in ['Route', 'HttpGet', 'HttpPost', 'HttpPut', 'HttpDelete', 'HttpPatch']:
                        args = attr.get('arguments', [])
                        if args:
                            return args[0].strip('"\'')
        
        # Check signature for endpoint patterns (e.g., "GET /api/users/{id}")
        if symbol.signature:
            # Pattern for explicit endpoint signatures
            endpoint_match = re.match(r'^(GET|POST|PUT|DELETE|PATCH)\s+(/[^\s]+)', symbol.signature)
            if endpoint_match:
                return endpoint_match.group(2)
        
        # Fallback: try to extract from documentation
        if symbol.documentation:
            route_match = re.search(r'\[Route\("([^"]+)"\)\]', symbol.documentation)
            if route_match:
                return route_match.group(1)
            
            http_match = re.search(r'\[Http(?:Get|Post|Put|Delete|Patch)\("([^"]+)"\)\]', symbol.documentation)
            if http_match:
                return http_match.group(1)
            
            # API Endpoint pattern in documentation
            api_match = re.search(r'API Endpoint:\s*\w+\s+(/[^\s\n]+)', symbol.documentation)
            if api_match:
                return api_match.group(1)
        
        return None
    
    def _exact_match(self, url1: str, url2: str) -> bool:
        """Check if two URL patterns match exactly (ignoring parameter names)."""
        # Normalize URLs
        norm1 = self._normalize_url_pattern(url1)
        norm2 = self._normalize_url_pattern(url2)
        
        return norm1 == norm2
    
    def _normalize_url_pattern(self, url: str) -> str:
        """
        Normalize URL pattern for comparison.
        
        Examples:
            /api/users/{id} -> /api/users/*
            /api/users/:id -> /api/users/*
            /api/users/123 -> /api/users/*
        """
        # Remove leading/trailing slashes
        url = url.strip('/')
        
        # Replace path parameters with wildcard
        url = re.sub(r'\{[^}]+\}', '*', url)  # {id} -> *
        url = re.sub(r':[^/]+', '*', url)      # :id -> *
        url = re.sub(r'\d+', '*', url)         # 123 -> *
        
        return url.lower()
    
    def _path_similarity(self, url1: str, url2: str) -> float:
        """Calculate similarity between two URL paths using sequence matching."""
        norm1 = self._normalize_url_pattern(url1)
        norm2 = self._normalize_url_pattern(url2)
        
        return SequenceMatcher(None, norm1, norm2).ratio()
    
    def _http_method_matches(self, call_method: str, endpoint: Symbol) -> bool:
        """Check if HTTP method matches the endpoint."""
        call_method_upper = call_method.upper()
        
        # Check structured_docs for HTTP method
        if endpoint.structured_docs:
            endpoint_method = endpoint.structured_docs.get('http_method', '')
            if endpoint_method and call_method_upper == endpoint_method.upper():
                return True
            
            # Check attributes for HTTP method decorators
            attributes = endpoint.structured_docs.get('attributes', [])
            for attr in attributes:
                attr_name = attr.get('name', '')
                if attr_name == f'Http{call_method.capitalize()}':
                    return True
        
        # Check signature for endpoint method (e.g., "GET /api/users")
        if endpoint.signature:
            if endpoint.signature.upper().startswith(call_method_upper + ' '):
                return True
        
        # Fallback: check symbol name for method hints
        symbol_name = endpoint.name.lower()
        call_method_lower = call_method.lower()
        
        # Check if method name contains HTTP verb
        if call_method_lower in symbol_name:
            return True
        
        # Check for common patterns
        method_patterns = {
            'get': ['get', 'fetch', 'retrieve', 'list', 'find', 'load'],
            'post': ['post', 'create', 'add', 'insert', 'save', 'submit'],
            'put': ['put', 'update', 'modify', 'edit', 'change'],
            'delete': ['delete', 'remove', 'destroy', 'erase'],
            'patch': ['patch', 'partial', 'modify'],
        }
        
        if call_method_lower in method_patterns:
            for pattern in method_patterns[call_method_lower]:
                if pattern in symbol_name:
                    return True
        
        # If no HTTP method info available, assume match (we'll rely on URL matching)
        if not endpoint.structured_docs or 'http_method' not in endpoint.structured_docs:
            return True
        
        return False
    
    async def link_events(self, repository_ids: Optional[List[int]] = None) -> int:
        """
        Link event publishers to their subscribers.
        
        This connects message publishers to their consumers across repositories,
        enabling understanding of event-driven communication patterns.
        
        Args:
            repository_ids: Optional list of repository IDs to process
            
        Returns:
            Number of event links created
        """
        # Fetch publishers
        query_pub = select(PublishedEvent)
        if repository_ids:
            query_pub = query_pub.where(PublishedEvent.repository_id.in_(repository_ids))
        
        pub_result = await self.db.execute(query_pub)
        publishers = pub_result.scalars().all()
        
        # Fetch subscribers
        query_sub = select(EventSubscription)
        if repository_ids:
            query_sub = query_sub.where(EventSubscription.repository_id.in_(repository_ids))
        
        sub_result = await self.db.execute(query_sub)
        subscribers = sub_result.scalars().all()
        
        if not publishers or not subscribers:
            logger.info("no_events_to_link", publishers=len(publishers), subscribers=len(subscribers))
            return 0
        
        links_created = 0
        
        for publisher in publishers:
            for subscriber in subscribers:
                # Skip same-repository links (usually internal calls, not events)
                if publisher.repository_id == subscriber.repository_id:
                    continue
                
                match_result = self._match_event(publisher, subscriber)
                
                if match_result:
                    confidence, method, metadata = match_result
                    
                    # Check for existing link
                    existing = await self.db.execute(
                        select(EventLink).where(
                            EventLink.published_event_id == publisher.id,
                            EventLink.event_subscription_id == subscriber.id
                        )
                    )
                    if existing.scalar_one_or_none():
                        continue
                    
                    # Create link
                    link = EventLink(
                        published_event_id=publisher.id,
                        publisher_repository_id=publisher.repository_id,
                        event_subscription_id=subscriber.id,
                        subscriber_repository_id=subscriber.repository_id,
                        match_confidence=int(confidence * 100),
                        match_method=method,
                        match_metadata=metadata
                    )
                    
                    self.db.add(link)
                    links_created += 1
        
        if links_created > 0:
            await self.db.flush()
        
        logger.info("event_linking_complete", total_links=links_created)
        return links_created
    
    def _match_event(
        self,
        publisher: PublishedEvent,
        subscriber: EventSubscription
    ) -> Optional[Tuple[float, str, Dict]]:
        """
        Match a published event to a subscription.
        
        Returns:
            Tuple of (confidence, method, metadata) or None
        """
        score = 0.0
        method = 'unknown'
        metadata = {}
        
        # 1. Exact event type name match (70% weight)
        if publisher.event_type_name == subscriber.event_type_name:
            score += 0.7
            method = 'exact_type'
            metadata['type_match'] = 'exact'
        else:
            # Fuzzy event type match
            similarity = SequenceMatcher(
                None,
                publisher.event_type_name.lower(),
                subscriber.event_type_name.lower()
            ).ratio()
            
            if similarity >= 0.8:
                score += 0.7 * similarity
                method = 'fuzzy_type'
                metadata['type_match'] = 'fuzzy'
                metadata['type_similarity'] = similarity
        
        # 2. Topic/Queue name match (20% weight)
        if publisher.topic_name and subscriber.queue_name:
            if publisher.topic_name == subscriber.queue_name:
                score += 0.2
                metadata['topic_match'] = True
        
        # 3. Routing key match for RabbitMQ (10% weight)
        if publisher.routing_key and subscriber.subscription_pattern:
            if self._routing_key_matches(publisher.routing_key, subscriber.subscription_pattern):
                score += 0.1
                metadata['routing_key_match'] = True
        
        # Only return if confidence meets threshold
        threshold = self.EVENT_CONFIDENCE_THRESHOLD / 100.0
        if score >= threshold:
            return (score, method, metadata)
        
        # Log near-misses for threshold tuning (scores between 50% and threshold)
        if 0.5 <= score < threshold:
            logger.info(
                "event_link_near_miss",
                publisher_event=publisher.event_type_name,
                subscriber_event=subscriber.event_type_name,
                publisher_repo_id=publisher.repository_id,
                subscriber_repo_id=subscriber.repository_id,
                score=round(score * 100, 1),
                threshold=self.EVENT_CONFIDENCE_THRESHOLD,
                metadata=metadata
            )
        
        return None
    
    def _routing_key_matches(self, routing_key: str, pattern: str) -> bool:
        """Check if routing key matches subscription pattern (RabbitMQ style)."""
        # Convert RabbitMQ pattern to regex
        # * matches exactly one word
        # # matches zero or more words
        regex_pattern = pattern.replace('.', r'\.')
        regex_pattern = regex_pattern.replace('*', r'[^.]+')
        regex_pattern = regex_pattern.replace('#', r'.*')
        regex_pattern = f'^{regex_pattern}$'
        
        return bool(re.match(regex_pattern, routing_key))
    
    async def get_connected_endpoints(
        self,
        symbol_id: int
    ) -> Dict[str, Any]:
        """
        Get all connected endpoints for a symbol.
        
        This is the key method for enriching get_symbol_context with cross-service
        information. It returns:
        - Outgoing API calls from this symbol and their linked backend endpoints
        - Events published by this symbol and their subscribers
        - Events subscribed to by this symbol and their publishers
        - API endpoints that call this symbol
        
        Args:
            symbol_id: The symbol ID to get connections for
            
        Returns:
            Dictionary with connected endpoints information
        """
        connections = {
            'outgoing_api_calls': [],
            'incoming_api_calls': [],
            'published_events': [],
            'subscribed_events': [],
        }
        
        # 1. Get outgoing API calls from this symbol
        outgoing_result = await self.db.execute(
            select(OutgoingApiCall, ApiEndpointLink, Symbol, File, Repository)
            .outerjoin(ApiEndpointLink, OutgoingApiCall.id == ApiEndpointLink.outgoing_call_id)
            .outerjoin(Symbol, ApiEndpointLink.target_symbol_id == Symbol.id)
            .outerjoin(File, Symbol.file_id == File.id)
            .outerjoin(Repository, File.repository_id == Repository.id)
            .where(OutgoingApiCall.symbol_id == symbol_id)
        )
        
        for row in outgoing_result.all():
            call, link, target_symbol, target_file, target_repo = row
            call_info = {
                'http_method': call.http_method,
                'url_pattern': call.url_pattern,
                'call_type': call.call_type,
                'line_number': call.line_number,
            }
            
            if link and target_symbol:
                call_info['linked_endpoint'] = {
                    'symbol_id': target_symbol.id,
                    'name': target_symbol.name,
                    'fully_qualified_name': target_symbol.fully_qualified_name,
                    'signature': target_symbol.signature,
                    'repository': target_repo.name if target_repo else None,
                    'file': target_file.path if target_file else None,
                    'match_confidence': link.match_confidence,
                    'match_method': link.match_method,
                }
            
            connections['outgoing_api_calls'].append(call_info)
        
        # 2. Get incoming API calls to this symbol (if it's an endpoint)
        incoming_result = await self.db.execute(
            select(ApiEndpointLink, OutgoingApiCall, File, Repository)
            .join(OutgoingApiCall, ApiEndpointLink.outgoing_call_id == OutgoingApiCall.id)
            .join(File, OutgoingApiCall.file_id == File.id)
            .join(Repository, File.repository_id == Repository.id)
            .where(ApiEndpointLink.target_symbol_id == symbol_id)
        )
        
        for row in incoming_result.all():
            link, call, source_file, source_repo = row
            connections['incoming_api_calls'].append({
                'http_method': call.http_method,
                'url_pattern': call.url_pattern,
                'call_type': call.call_type,
                'source_repository': source_repo.name,
                'source_file': source_file.path,
                'line_number': call.line_number,
                'match_confidence': link.match_confidence,
                'match_method': link.match_method,
            })
        
        # 3. Get published events from this symbol
        pub_result = await self.db.execute(
            select(PublishedEvent, EventLink, EventSubscription, Repository)
            .outerjoin(EventLink, PublishedEvent.id == EventLink.published_event_id)
            .outerjoin(EventSubscription, EventLink.event_subscription_id == EventSubscription.id)
            .outerjoin(Repository, EventSubscription.repository_id == Repository.id)
            .where(PublishedEvent.symbol_id == symbol_id)
        )
        
        for row in pub_result.all():
            event, link, subscription, sub_repo = row
            event_info = {
                'event_type': event.event_type_name,
                'messaging_library': event.messaging_library,
                'topic': event.topic_name,
                'line_number': event.line_number,
                'subscribers': []
            }
            
            if link and subscription:
                event_info['subscribers'].append({
                    'handler_class': subscription.handler_class_name,
                    'queue': subscription.queue_name,
                    'repository': sub_repo.name if sub_repo else None,
                    'match_confidence': link.match_confidence,
                })
            
            # Merge subscribers for same event
            existing = next(
                (e for e in connections['published_events'] 
                 if e['event_type'] == event.event_type_name),
                None
            )
            if existing:
                existing['subscribers'].extend(event_info['subscribers'])
            else:
                connections['published_events'].append(event_info)
        
        # 4. Get subscribed events handled by this symbol
        sub_result = await self.db.execute(
            select(EventSubscription, EventLink, PublishedEvent, Repository)
            .outerjoin(EventLink, EventSubscription.id == EventLink.event_subscription_id)
            .outerjoin(PublishedEvent, EventLink.published_event_id == PublishedEvent.id)
            .outerjoin(Repository, PublishedEvent.repository_id == Repository.id)
            .where(EventSubscription.symbol_id == symbol_id)
        )
        
        for row in sub_result.all():
            subscription, link, event, pub_repo = row
            sub_info = {
                'event_type': subscription.event_type_name,
                'messaging_library': subscription.messaging_library,
                'queue': subscription.queue_name,
                'handler_class': subscription.handler_class_name,
                'publishers': []
            }
            
            if link and event:
                sub_info['publishers'].append({
                    'event_type': event.event_type_name,
                    'topic': event.topic_name,
                    'repository': pub_repo.name if pub_repo else None,
                    'match_confidence': link.match_confidence,
                })
            
            # Merge publishers for same subscription
            existing = next(
                (s for s in connections['subscribed_events']
                 if s['event_type'] == subscription.event_type_name),
                None
            )
            if existing:
                existing['publishers'].extend(sub_info['publishers'])
            else:
                connections['subscribed_events'].append(sub_info)
        
        return connections
    
    async def link_all(
        self,
        repository_ids: Optional[List[int]] = None
    ) -> Dict[str, int]:
        """
        Run the complete linking process for all microservices.
        
        This is the main orchestration method that:
        1. Parses all gateway configurations
        2. Links outgoing API calls to backend endpoints
        3. Links event publishers to subscribers
        
        Args:
            repository_ids: Optional list of repository IDs to process
            
        Returns:
            Dictionary with counts of created links
        """
        results = {
            'gateway_routes_parsed': 0,
            'api_links_created': 0,
            'event_links_created': 0,
        }
        
        logger.info("link_all_started", repository_ids=repository_ids)
        
        try:
            # Step 1: Parse gateway configurations
            gateway_routes = await self.parse_all_gateway_configs(repository_ids)
            results['gateway_routes_parsed'] = len(gateway_routes)
            
            # Step 2: Link API calls to endpoints
            api_links = await self.link_api_calls_to_endpoints(repository_ids, gateway_routes)
            results['api_links_created'] = api_links
            
            # Step 3: Link events
            event_links = await self.link_events(repository_ids)
            results['event_links_created'] = event_links
            
            logger.info(
                "link_all_completed",
                **results
            )
            
        except Exception as e:
            logger.error("link_all_failed", error=str(e))
            raise
        
        return results


async def get_connected_endpoints_for_symbol(
    db: AsyncSession,
    symbol_id: int
) -> Dict[str, Any]:
    """
    Standalone function to get connected endpoints for a symbol.
    
    This is a convenience function that creates a LinkService and calls
    get_connected_endpoints. Use this from outside the LinkService class.
    
    Args:
        db: AsyncSession for database operations
        symbol_id: The symbol ID to get connections for
        
    Returns:
        Dictionary with connected endpoints information
    """
    service = LinkService(db)
    return await service.get_connected_endpoints(symbol_id)
