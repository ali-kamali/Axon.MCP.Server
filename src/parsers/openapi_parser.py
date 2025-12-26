"""OpenAPI/Swagger specification parser."""

import json
import yaml
from typing import List, Optional, Dict, Any
from pathlib import Path

from src.config.enums import LanguageEnum, SymbolKindEnum
from src.parsers.base_parser import BaseParser, ParseResult, ParsedSymbol


class OpenAPIParser(BaseParser):
    """Parser for OpenAPI/Swagger specification files."""
    
    def __init__(self):
        self.language = LanguageEnum.UNKNOWN  # API specs are language-agnostic
    
    def get_language(self) -> LanguageEnum:
        """Return the language this parser handles."""
        return self.language
    
    def is_supported(self, file_path: Path) -> bool:
        """Check if file is an OpenAPI spec."""
        name = file_path.name.lower()
        
        # Common OpenAPI file names
        openapi_names = [
            'openapi.json', 'openapi.yaml', 'openapi.yml',
            'swagger.json', 'swagger.yaml', 'swagger.yml',
            'api-spec.json', 'api-spec.yaml', 'api-spec.yml'
        ]
        
        return name in openapi_names or name.startswith('openapi') or name.startswith('swagger')
    
    def parse(self, code: str, file_path: Optional[str] = None) -> ParseResult:
        """
        Parse OpenAPI specification and extract API contracts.
        
        Extracts:
        - API endpoints (paths)
        - Request/response schemas
        - Components/definitions
        - Security schemes
        """
        import time
        start_time = time.time()
        
        symbols = []
        errors = []
        
        try:
            # Try to parse as JSON first
            try:
                spec = json.loads(code)
            except json.JSONDecodeError:
                # Try YAML
                spec = yaml.safe_load(code)
            
            # Extract API metadata
            symbols.extend(self._extract_metadata(spec, file_path))
            
            # Extract paths (endpoints)
            if 'paths' in spec:
                symbols.extend(self._extract_paths(spec['paths'], file_path))
            
            # Extract components/definitions (schemas)
            if 'components' in spec and 'schemas' in spec['components']:
                symbols.extend(self._extract_schemas(spec['components']['schemas'], file_path))
            elif 'definitions' in spec:  # OpenAPI 2.0 (Swagger)
                symbols.extend(self._extract_schemas(spec['definitions'], file_path))
            
            # Extract security schemes
            if 'components' in spec and 'securitySchemes' in spec['components']:
                symbols.extend(self._extract_security_schemes(spec['components']['securitySchemes'], file_path))
            elif 'securityDefinitions' in spec:  # OpenAPI 2.0
                symbols.extend(self._extract_security_schemes(spec['securityDefinitions'], file_path))
            
        except Exception as e:
            errors.append(f"OpenAPI parsing error: {str(e)}")
        
        duration_ms = (time.time() - start_time) * 1000
        
        return ParseResult(
            language=self.language,
            file_path=file_path or "unknown",
            symbols=symbols,
            imports=[],
            exports=[],
            parse_errors=errors,
            parse_duration_ms=duration_ms
        )
    
    def _extract_metadata(self, spec: Dict, file_path: Optional[str]) -> List[ParsedSymbol]:
        """Extract API metadata (title, version, description)."""
        symbols = []
        
        if 'info' in spec:
            info = spec['info']
            
            # API Title
            if 'title' in info:
                symbols.append(ParsedSymbol(
                    kind=SymbolKindEnum.PROPERTY,
                    name='API_TITLE',
                    start_line=0,
                    end_line=0,
                    start_column=0,
                    end_column=0,
                    signature=f"API: {info['title']}",
                    documentation=info.get('description', ''),
                    structured_docs={
                        'type': 'api_metadata',
                        'title': info['title'],
                        'version': info.get('version', 'unknown'),
                        'description': info.get('description', '')
                    }
                ))
        
        return symbols
    
    def _extract_paths(self, paths: Dict, file_path: Optional[str]) -> List[ParsedSymbol]:
        """Extract API endpoints from paths."""
        symbols = []
        
        for path, path_item in paths.items():
            # Each path can have multiple operations (get, post, put, etc.)
            for method, operation in path_item.items():
                if method.lower() not in ['get', 'post', 'put', 'delete', 'patch', 'options', 'head']:
                    continue
                
                operation_id = operation.get('operationId', f"{method.upper()}_{path}")
                summary = operation.get('summary', '')
                description = operation.get('description', '')
                
                # Extract parameters
                parameters = []
                if 'parameters' in operation:
                    for param in operation['parameters']:
                        parameters.append({
                            'name': param.get('name', 'unknown'),
                            'in': param.get('in', 'unknown'),  # query, path, header, cookie
                            'required': param.get('required', False),
                            'type': param.get('schema', {}).get('type', 'unknown') if 'schema' in param else param.get('type', 'unknown')
                        })
                
                # Extract request body
                request_schema = None
                if 'requestBody' in operation:
                    content = operation['requestBody'].get('content', {})
                    if 'application/json' in content:
                        request_schema = content['application/json'].get('schema', {}).get('$ref', 'unknown')
                
                # Extract responses
                responses = []
                if 'responses' in operation:
                    for status_code, response in operation['responses'].items():
                        responses.append({
                            'status': status_code,
                            'description': response.get('description', '')
                        })
                
                symbols.append(ParsedSymbol(
                    kind=SymbolKindEnum.FUNCTION,  # Endpoints as functions
                    name=operation_id,
                    start_line=0,
                    end_line=0,
                    start_column=0,
                    end_column=0,
                    signature=f"{method.upper()} {path}",
                    documentation=f"{summary}\n\n{description}" if summary or description else None,
                    structured_docs={
                        'type': 'api_endpoint',
                        'method': method.upper(),
                        'path': path,
                        'operationId': operation_id,
                        'summary': summary,
                        'description': description,
                        'parameters': parameters,
                        'requestSchema': request_schema,
                        'responses': responses,
                        'tags': operation.get('tags', []),
                        'security': operation.get('security', [])
                    },
                    parameters=parameters
                ))
        
        return symbols
    
    def _extract_schemas(self, schemas: Dict, file_path: Optional[str]) -> List[ParsedSymbol]:
        """Extract data schemas/models."""
        symbols = []
        
        for schema_name, schema_def in schemas.items():
            # Extract properties
            properties = []
            if 'properties' in schema_def:
                for prop_name, prop_def in schema_def['properties'].items():
                    properties.append({
                        'name': prop_name,
                        'type': prop_def.get('type', 'unknown'),
                        'format': prop_def.get('format'),
                        'description': prop_def.get('description', '')
                    })
            
            # Extract required fields
            required = schema_def.get('required', [])
            
            symbols.append(ParsedSymbol(
                kind=SymbolKindEnum.CLASS,  # Schemas as classes
                name=schema_name,
                start_line=0,
                end_line=0,
                start_column=0,
                end_column=0,
                signature=f"Schema: {schema_name}",
                documentation=schema_def.get('description', f"Data schema for {schema_name}"),
                structured_docs={
                    'type': 'api_schema',
                    'schema_name': schema_name,
                    'properties': properties,
                    'required': required,
                    'schema_type': schema_def.get('type', 'object')
                }
            ))
        
        return symbols
    
    def _extract_security_schemes(self, schemes: Dict, file_path: Optional[str]) -> List[ParsedSymbol]:
        """Extract security schemes."""
        symbols = []
        
        for scheme_name, scheme_def in schemes.items():
            scheme_type = scheme_def.get('type', 'unknown')
            
            symbols.append(ParsedSymbol(
                kind=SymbolKindEnum.PROPERTY,
                name=f"Security_{scheme_name}",
                start_line=0,
                end_line=0,
                start_column=0,
                end_column=0,
                signature=f"Security Scheme: {scheme_name} ({scheme_type})",
                documentation=scheme_def.get('description', f"Security scheme: {scheme_name}"),
                structured_docs={
                    'type': 'security_scheme',
                    'scheme_name': scheme_name,
                    'scheme_type': scheme_type,
                    'scheme': scheme_def.get('scheme'),
                    'bearerFormat': scheme_def.get('bearerFormat'),
                    'in': scheme_def.get('in'),
                    'name': scheme_def.get('name')
                }
            ))
        
        return symbols

