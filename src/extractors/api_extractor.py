"""API endpoint extractor for Web APIs."""

from typing import List, Dict, Any, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Symbol, File, Repository
from src.config.enums import SymbolKindEnum, LanguageEnum, AccessModifierEnum


class ApiEndpoint:
    """Represents an API endpoint."""
    
    def __init__(
        self,
        http_method: str,
        route: str,
        controller: str,
        action: str,
        file_path: str,
        file_id: int,
        language: LanguageEnum,
        line_number: int,
        requires_auth: bool = False,
        parameters: Optional[List[Dict]] = None,
    ):
        self.http_method = http_method
        self.route = route
        self.controller = controller
        self.action = action
        self.file_path = file_path
        self.file_id = file_id
        self.language = language
        self.line_number = line_number
        self.requires_auth = requires_auth
        self.parameters = parameters or []


class ApiEndpointExtractor:
    """Extracts API endpoints from parsed code."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def extract_endpoints(
        self,
        repository_id: int
    ) -> List[ApiEndpoint]:
        """
        Extract all API endpoints from a repository.
        
        Args:
            repository_id: Repository ID
            
        Returns:
            List of API endpoints
        """
        from src.utils.logging_config import get_logger
        logger = get_logger(__name__)
        
        endpoints = []
        
        # Find all controller classes (classes with [ApiController] or names ending in Controller)
        result = await self.session.execute(
            select(Symbol, File)
            .join(File, Symbol.file_id == File.id)
            .where(
                File.repository_id == repository_id,
                Symbol.kind == SymbolKindEnum.CLASS
            )
        )
        
        all_classes = result.all()
        logger.info(f"api_extractor_found_classes", count=len(all_classes), repository_id=repository_id)
        
        controller_count = 0
        for class_symbol, file in all_classes:
            is_controller = self._is_controller(class_symbol)
            
            if is_controller:
                controller_count += 1
                logger.debug(f"api_extractor_controller_found", 
                           name=class_symbol.name, 
                           fqn=class_symbol.fully_qualified_name,
                           file=file.path)
                
                # Extract class-level route
                class_route = self._extract_route_from_attributes(class_symbol)
                
                # Find all methods in this class
                methods_result = await self.session.execute(
                    select(Symbol)
                    .where(
                        Symbol.file_id == class_symbol.file_id,
                        Symbol.kind == SymbolKindEnum.METHOD,
                        Symbol.parent_name == class_symbol.fully_qualified_name
                    )
                )
                
                methods = methods_result.scalars().all()
                logger.debug(f"api_extractor_methods_found", 
                           controller=class_symbol.name,
                           method_count=len(methods))
                
                for method in methods:
                    logger.debug(f"api_extractor_checking_method",
                               symbol_name=method.name,
                               has_attributes=bool(method.structured_docs and 'attributes' in method.structured_docs))
                    
                    endpoint = self._extract_endpoint_from_method(
                        method,
                        class_symbol,
                        class_route,
                        file.path,
                        file.id,
                        file.language
                    )
                    if endpoint:
                        logger.info(f"api_extractor_endpoint_created",
                                  http_method=endpoint.http_method,
                                  route=endpoint.route,
                                  controller=endpoint.controller)
                        endpoints.append(endpoint)
                    else:
                        logger.debug(f"api_extractor_method_skipped",
                                   symbol_name=method.name,
                                   reason="no_http_method_attribute")
        
        logger.info(f"api_extractor_controllers_processed", 
                   controller_count=controller_count,
                   endpoints_from_controllers=len(endpoints))

        # Also find explicitly defined endpoints (e.g. Minimal APIs)
        # These are already parsed as SymbolKindEnum.ENDPOINT
        endpoints_result = await self.session.execute(
            select(Symbol, File)
            .join(File, Symbol.file_id == File.id)
            .where(
                File.repository_id == repository_id,
                Symbol.kind == SymbolKindEnum.ENDPOINT
            )
        )

        minimal_api_symbols = endpoints_result.all()
        logger.info(f"api_extractor_minimal_apis_found", count=len(minimal_api_symbols))

        for symbol, file in minimal_api_symbols:
            # Convert Symbol to ApiEndpoint
            # Parse name "METHOD /route"
            parts = symbol.name.split(' ', 1)
            if len(parts) == 2:
                http_method, route = parts
            else:
                # Fallback if name format is unexpected
                http_method = "UNKNOWN" 
                route = symbol.name

            # Extract structured docs info if available
            docs = symbol.structured_docs or {}
            
            endpoint = ApiEndpoint(
                http_method=docs.get('method', http_method),
                route=docs.get('path', route),
                controller=docs.get('type', 'MinimalApi'), # Use type as controller name for grouping
                action=symbol.name,
                file_path=file.path,
                file_id=file.id,
                language=file.language,
                line_number=symbol.start_line,
                requires_auth=False, # Could extract from attributes if we parsed them for endpoints
                parameters=[] # Could extract from signature/docs
            )
            endpoints.append(endpoint)
        
        logger.info(f"api_extractor_total_endpoints", 
                   total=len(endpoints),
                   from_controllers=len(endpoints) - len(minimal_api_symbols),
                   from_minimal_apis=len(minimal_api_symbols))
        
        return endpoints

    async def save_endpoints(self, endpoints: List[ApiEndpoint]) -> int:
        """
        Save extracted endpoints as Symbol records.
        
        Args:
            endpoints: List of ApiEndpoint objects
            
        Returns:
            Count of saved endpoints
        """
        count = 0
        for endpoint in endpoints:
            # Create a unique name for the endpoint symbol
            # e.g., "GET /api/users/{id}"
            name = f"{endpoint.http_method} {endpoint.route}"
            
            # Create Symbol
            symbol = Symbol(
                file_id=endpoint.file_id,
                language=endpoint.language,
                kind=SymbolKindEnum.ENDPOINT,
                access_modifier=AccessModifierEnum.PUBLIC,
                name=name,
                fully_qualified_name=f"{endpoint.controller}.{endpoint.action}:{endpoint.http_method}",
                start_line=endpoint.line_number,
                end_line=endpoint.line_number, # Approximate
                signature=f"{endpoint.http_method} {endpoint.route}",
                documentation=f"API Endpoint: {endpoint.http_method} {endpoint.route}\nController: {endpoint.controller}\nAction: {endpoint.action}",
                structured_docs={
                    "type": "api_endpoint",
                    "http_method": endpoint.http_method,
                    "route": endpoint.route,
                    "controller": endpoint.controller,
                    "action": endpoint.action,
                    "requires_auth": endpoint.requires_auth,
                    "parameters": endpoint.parameters
                },
                is_generated=1 # Mark as generated since it's derived
            )
            
            self.session.add(symbol)
            count += 1
            
        return count
    
    def _is_controller(self, class_symbol: Symbol) -> bool:
        """Check if a class is a controller."""
        from src.utils.logging_config import get_logger
        logger = get_logger(__name__)
        
        # Check by name
        name_check = class_symbol.name.endswith('Controller')
        
        # Check by attributes
        attribute_check = False
        has_structured_docs = class_symbol.structured_docs is not None
        has_attributes = False
        attribute_names = []
        
        if has_structured_docs and 'attributes' in class_symbol.structured_docs:
            has_attributes = True
            attrs = class_symbol.structured_docs['attributes']
            attribute_names = [attr.get('name') for attr in attrs]
            attribute_check = any(name in ['ApiController', 'Controller'] for name in attribute_names)
        
        is_controller = name_check or attribute_check
        
        # Log details for first few classes to understand the pattern
        logger.debug(f"_is_controller_check",
                    class_name=class_symbol.name,
                    name_check=name_check,
                    has_structured_docs=has_structured_docs,
                    has_attributes=has_attributes,
                    attribute_names=attribute_names,
                    attribute_check=attribute_check,
                    is_controller=is_controller)
        
        return is_controller
    
    def _extract_route_from_attributes(self, symbol: Symbol) -> str:
        """Extract route from symbol attributes."""
        if not symbol.structured_docs or 'attributes' not in symbol.structured_docs:
            return ""
        
        attrs = symbol.structured_docs['attributes']
        route = ""
        area_name = ""
        
        # First pass: find Area attribute
        for attr in attrs:
            if attr.get('name') == 'Area':
                args = attr.get('arguments', {})
                # Handle structured arguments (dict) or legacy (list)
                if isinstance(args, dict):
                    positional = args.get('positional', [])
                    if positional:
                        area_name = str(positional[0]).strip('"\'')
                elif isinstance(args, list) and args:
                    area_name = args[0].strip('"\'')
        
        # Second pass: find Route attribute
        for attr in attrs:
            if attr.get('name') == 'Route':
                # Get the route template
                args = attr.get('arguments', {})
                current_route = ""
                
                if isinstance(args, dict):
                    # Check named 'Template' argument
                    if 'Template' in args.get('named', {}):
                        current_route = str(args['named']['Template']).strip('"\'')
                    # Check positional
                    elif args.get('positional'):
                        current_route = str(args['positional'][0]).strip('"\'')
                elif isinstance(args, list) and args:
                    current_route = args[0].strip('"\'')
                
                if current_route:
                    route = current_route
                    
                    # Handle [controller] placeholder
                    if '[controller]' in route:
                        controller_name = symbol.name.replace('Controller', '')
                        route = route.replace('[controller]', controller_name)
                        
                    # Handle [area] placeholder
                    if '[area]' in route and area_name:
                        route = route.replace('[area]', area_name)
                        
                    return route
        
        return ""
    
    def _extract_endpoint_from_method(
        self,
        method: Symbol,
        controller: Symbol,
        class_route: str,
        file_path: str,
        file_id: int,
        language: LanguageEnum
    ) -> Optional[ApiEndpoint]:
        """Extract API endpoint from a method."""
        if not method.structured_docs or 'attributes' not in method.structured_docs:
            return None
        
        attrs = method.structured_docs['attributes']
        http_method = None
        method_route = ""
        requires_auth = False
        
        # Check for HTTP method attributes
        for attr in attrs:
            attr_name = attr.get('name', '')
            
            # HTTP method attributes
            if attr_name == 'HttpGet':
                http_method = 'GET'
                method_route = self._get_route_from_attribute(attr)
            elif attr_name == 'HttpPost':
                http_method = 'POST'
                method_route = self._get_route_from_attribute(attr)
            elif attr_name == 'HttpPut':
                http_method = 'PUT'
                method_route = self._get_route_from_attribute(attr)
            elif attr_name == 'HttpDelete':
                http_method = 'DELETE'
                method_route = self._get_route_from_attribute(attr)
            elif attr_name == 'HttpPatch':
                http_method = 'PATCH'
                method_route = self._get_route_from_attribute(attr)
            elif attr_name in ['Route']:
                # Only use Route attribute if HTTP method is already found or implied?
                # Usually Route is used with HttpMethod, or on its own (implies GET? No).
                # But if we found HttpMethod, we might have already set method_route.
                # If we haven't found HttpMethod, Route doesn't define it.
                # But sometimes [Route("...")] is used on method.
                # Let's assume if we find Route on method, we might need to infer method or wait for HttpVerb.
                # For now, just extract route.
                r = self._get_route_from_attribute(attr)
                if r:
                    method_route = r
            
            # Authorization
            if attr_name in ['Authorize', 'Authenticated']:
                requires_auth = True
        
        if not http_method:
            return None
        
        # Combine routes
        full_route = self._combine_routes(class_route, method_route)
        
        # Extract parameters
        parameters = []
        if method.parameters:
            for param in method.parameters:
                if isinstance(param, dict):
                    parameters.append(param)
        
        return ApiEndpoint(
            http_method=http_method,
            route=full_route,
            controller=controller.name,
            action=method.name,
            file_path=file_path,
            file_id=file_id,
            language=language,
            line_number=method.start_line,
            requires_auth=requires_auth,
            parameters=parameters
        )
    
    def _get_route_from_attribute(self, attr: Dict) -> str:
        """Extract route string from attribute."""
        args = attr.get('arguments', {})
        if isinstance(args, dict):
            # Check named 'Template' argument
            if 'Template' in args.get('named', {}):
                return str(args['named']['Template']).strip('"\'')
            # Check positional
            elif args.get('positional'):
                return str(args['positional'][0]).strip('"\'')
        elif isinstance(args, list) and args:
            # Remove quotes
            return args[0].strip('"\'')
        return ""
    
    def _combine_routes(self, base_route: str, method_route: str) -> str:
        """Combine base and method routes."""
        if not base_route:
            base_route = ""
        if not method_route:
            method_route = ""
        
        # Ensure proper slashes
        if base_route and not base_route.startswith('/'):
            base_route = '/' + base_route
        
        if method_route and not method_route.startswith('/'):
            method_route = '/' + method_route
        
        # Combine
        full_route = base_route + method_route
        
        # Clean up double slashes
        while '//' in full_route:
            full_route = full_route.replace('//', '/')
        
        return full_route if full_route else '/'

