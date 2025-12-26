"""Nginx configuration parser.

Parses nginx.conf files to extract routing rules for linking frontend calls to backend endpoints.
"""

import re
from typing import List, Dict, Any, Optional
from pathlib import Path
import structlog

logger = structlog.get_logger(__name__)


class NginxParser:
    """Parser for Nginx configuration files."""
    
    def is_nginx_config(self, file_path: str) -> bool:
        """Check if file is an Nginx configuration file."""
        path = Path(file_path)
        return path.suffix == '.conf' or path.name in ['nginx.conf', 'default.conf']
    
    def parse_nginx_config(self, file_path: str, content: str) -> List[Dict[str, Any]]:
        """
        Parse Nginx configuration and extract routes.
        
        Args:
            file_path: Path to the configuration file
            content: File content as string
            
        Returns:
            List of route dictionaries
        """
        routes = []
        
        # Remove comments
        content = self._remove_comments(content)
        
        # Extract location blocks
        location_blocks = self._extract_location_blocks(content)
        
        for location in location_blocks:
            try:
                parsed_route = self._parse_location_block(location)
                if parsed_route:
                    routes.append(parsed_route)
            except Exception as e:
                logger.warning("nginx_location_parse_failed", location=location[:100], error=str(e))
                continue
        
        logger.info("nginx_config_parsed", file_path=file_path, routes_count=len(routes))
        return routes
    
    def _remove_comments(self, content: str) -> str:
        """Remove comments from Nginx config."""
        # Remove single-line comments
        content = re.sub(r'#.*$', '', content, flags=re.MULTILINE)
        return content
    
    def _extract_location_blocks(self, content: str) -> List[Dict[str, Any]]:
        """Extract all location blocks from Nginx config."""
        # Pattern to match location blocks
        # Supports: location /path { ... }
        #           location ~ /regex { ... }
        #           location ~* /case-insensitive { ... }
        pattern = r'location\s+([~*\s]*)(.*?)\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}'
        
        locations = []
        for match in re.finditer(pattern, content, re.DOTALL):
            modifier, path, block = match.groups()
            locations.append({
                'modifier': modifier.strip(),
                'path': path.strip(),
                'block': block.strip()
            })
        
        return locations
    
    def _parse_location_block(self, location: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse a single location block."""
        path = location['path']
        block = location['block']
        modifier = location['modifier']
        
        # Extract proxy_pass directive
        proxy_pass = self._extract_proxy_pass(block)
        if not proxy_pass:
            return None
        
        # Parse proxy_pass URL
        upstream_info = self._parse_proxy_pass_url(proxy_pass)
        if not upstream_info:
            return None
        
        # Determine if path is regex
        is_regex = '~' in modifier
        
        return {
            'downstream_path': path,
            'upstream_path': upstream_info.get('path'),
            'upstream_host': upstream_info.get('host'),
            'upstream_port': upstream_info.get('port'),
            'http_methods': [],  # Nginx doesn't specify methods in location
            'is_regex': is_regex,
            'metadata': {
                'modifier': modifier,
                'proxy_pass': proxy_pass,
                'block': block
            }
        }
    
    def _extract_proxy_pass(self, block: str) -> Optional[str]:
        """Extract proxy_pass directive from location block."""
        match = re.search(r'proxy_pass\s+([^;]+);', block)
        if match:
            return match.group(1).strip()
        return None
    
    def _parse_proxy_pass_url(self, proxy_pass: str) -> Optional[Dict[str, Any]]:
        """
        Parse proxy_pass URL to extract host, port, and path.
        
        Examples:
            http://backend:8080/api -> {host: backend, port: 8080, path: /api}
            http://service -> {host: service, port: 80, path: /}
            http://upstream_name/path -> {host: upstream_name, port: None, path: /path}
        """
        # Pattern to match proxy_pass URL
        pattern = r'(?:https?://)?([^:/]+)(?::(\d+))?(/.*)?$'
        match = re.match(pattern, proxy_pass)
        
        if not match:
            return None
        
        host, port, path = match.groups()
        
        return {
            'host': host,
            'port': int(port) if port else None,
            'path': path or '/'
        }
    
    def resolve_path_through_route(
        self,
        frontend_path: str,
        route: Dict[str, Any]
    ) -> Optional[str]:
        """
        Resolve a frontend path through an Nginx route to get the backend path.
        
        Args:
            frontend_path: The path from frontend code (e.g., '/api/users/123')
            route: Parsed Nginx route dictionary
            
        Returns:
            Backend path if route matches, None otherwise
        """
        downstream_path = route.get('downstream_path')
        upstream_path = route.get('upstream_path', '/')
        is_regex = route.get('is_regex', False)
        
        if not downstream_path:
            return None
        
        if is_regex:
            # Handle regex location
            try:
                match = re.match(downstream_path, frontend_path)
            except re.error as e:
                logger.warning("nginx_regex_error", pattern=downstream_path, error=str(e))
                return None
                
            if not match:
                return None
            
            # Replace captured groups in upstream path
            # IMPORTANT: Replace in reverse order (highest index first) to avoid
            # partial replacement issues (e.g., $12 being replaced as $1 + "2")
            backend_path = upstream_path
            groups = match.groups()
            for i in range(len(groups), 0, -1):
                captured = groups[i - 1]
                if captured is not None:
                    backend_path = backend_path.replace(f'${i}', captured)
            
            return backend_path
        else:
            # Handle exact/prefix location
            if frontend_path.startswith(downstream_path):
                # Replace prefix
                remaining_path = frontend_path[len(downstream_path):]
                backend_path = upstream_path.rstrip('/') + '/' + remaining_path.lstrip('/')
                # Clean up double slashes
                while '//' in backend_path:
                    backend_path = backend_path.replace('//', '/')
                return backend_path
        
        return None
