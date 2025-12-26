"""Ocelot API Gateway configuration parser.

Parses ocelot.json files to extract routing rules for linking frontend calls to backend endpoints.
"""

import json
import re
from typing import List, Dict, Any, Optional
from pathlib import Path
import structlog

logger = structlog.get_logger(__name__)


class OcelotParser:
    """Parser for Ocelot API Gateway configuration files."""
    
    def is_ocelot_config(self, file_path: str) -> bool:
        """Check if file is an Ocelot configuration file."""
        path = Path(file_path)
        return path.suffix == '.json' and 'ocelot' in path.name.lower()
    
    def parse_ocelot_config(self, file_path: str, content: str) -> List[Dict[str, Any]]:
        """
        Parse Ocelot configuration and extract routes.
        
        Args:
            file_path: Path to the configuration file
            content: File content as string
            
        Returns:
            List of route dictionaries
        """
        try:
            config = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error("ocelot_parse_failed", file_path=file_path, error=str(e))
            return []
        
        routes = []
        
        # Ocelot uses "Routes" array (or "ReRoutes" in older versions)
        route_list = config.get('Routes', config.get('ReRoutes', []))
        
        for route in route_list:
            try:
                parsed_route = self._parse_route(route)
                if parsed_route:
                    routes.append(parsed_route)
            except Exception as e:
                logger.warning("ocelot_route_parse_failed", route=route, error=str(e))
                continue
        
        logger.info("ocelot_config_parsed", file_path=file_path, routes_count=len(routes))
        return routes
    
    def _parse_route(self, route: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse a single Ocelot route configuration."""
        
        # Extract upstream (frontend-facing) path
        upstream_path = route.get('UpstreamPathTemplate')
        if not upstream_path:
            return None
        
        # Extract downstream (backend-facing) path
        downstream_path = route.get('DownstreamPathTemplate')
        
        # Extract host and port
        downstream_host_and_ports = route.get('DownstreamHostAndPorts', [])
        upstream_host = None
        upstream_port = None
        
        if downstream_host_and_ports and len(downstream_host_and_ports) > 0:
            first_host = downstream_host_and_ports[0]
            upstream_host = first_host.get('Host')
            upstream_port = first_host.get('Port')
        
        # Fallback to deprecated fields
        if not upstream_host:
            upstream_host = route.get('DownstreamHost')
        if not upstream_port:
            upstream_port = route.get('DownstreamPort')
        
        # Extract HTTP methods
        http_methods = route.get('UpstreamHttpMethod', [])
        if isinstance(http_methods, str):
            http_methods = [http_methods]
        
        # Extract route name/key
        route_name = route.get('Key') or route.get('RouteKey')
        
        # Extract priority
        priority = route.get('Priority', 0)
        
        return {
            'downstream_path': upstream_path,  # What frontend calls
            'upstream_path': downstream_path,  # What backend receives
            'upstream_host': upstream_host,
            'upstream_port': upstream_port,
            'http_methods': http_methods,
            'route_name': route_name,
            'priority': priority,
            'metadata': route  # Store full route config for reference
        }
    
    def resolve_path_through_route(
        self,
        frontend_path: str,
        route: Dict[str, Any]
    ) -> Optional[str]:
        """
        Resolve a frontend path through an Ocelot route to get the backend path.
        
        Args:
            frontend_path: The path from frontend code (e.g., '/api/users/123')
            route: Parsed Ocelot route dictionary
            
        Returns:
            Backend path if route matches, None otherwise
        """
        downstream_template = route.get('downstream_path')
        upstream_template = route.get('upstream_path')
        
        if not downstream_template or not upstream_template:
            return None
        
        # Extract placeholder names from the downstream template
        # Ocelot supports: {everything}, {url} (catch-all), {id}, {userId}, etc.
        placeholder_pattern = r'\{([^}]+)\}'
        placeholders = re.findall(placeholder_pattern, downstream_template)
        
        # Build regex pattern by replacing placeholders with capture groups
        # BEFORE escaping (so we don't have to deal with escaped braces)
        pattern = downstream_template
        
        # Catch-all placeholders match everything including slashes
        catch_all_names = {'everything', 'url', 'path', 'remainder'}
        
        for placeholder in placeholders:
            placeholder_token = '{' + placeholder + '}'
            if placeholder.lower() in catch_all_names:
                # Catch-all: matches everything including slashes
                pattern = pattern.replace(placeholder_token, '(.+)', 1)
            else:
                # Standard placeholder: matches until next slash
                pattern = pattern.replace(placeholder_token, '([^/]+)', 1)
        
        # Now escape special regex characters EXCEPT the capture groups we added
        # We need to escape the pattern carefully
        # Split by capture groups, escape the rest, rejoin
        parts = re.split(r'(\([^)]+\))', pattern)
        escaped_parts = []
        for part in parts:
            if part.startswith('(') and part.endswith(')'):
                # This is a capture group, keep as-is
                escaped_parts.append(part)
            else:
                # Escape special characters
                escaped_parts.append(re.escape(part))
        
        pattern = ''.join(escaped_parts)
        pattern = f'^{pattern}$'
        
        try:
            match = re.match(pattern, frontend_path)
        except re.error as e:
            logger.warning("ocelot_regex_error", pattern=pattern, error=str(e))
            return None
            
        if not match:
            return None
        
        # Replace placeholders in upstream template with captured values
        # Use the same placeholder order
        backend_path = upstream_template
        for i, (placeholder, captured_value) in enumerate(zip(placeholders, match.groups())):
            placeholder_token = '{' + placeholder + '}'
            backend_path = backend_path.replace(placeholder_token, captured_value, 1)
        
        return backend_path
