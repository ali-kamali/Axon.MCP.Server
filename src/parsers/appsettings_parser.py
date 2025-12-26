"""Parser for appsettings.json files."""

import json
from typing import List, Optional, Any, Dict
from pathlib import Path
from src.config.enums import LanguageEnum, SymbolKindEnum
from src.parsers.base_parser import BaseParser, ParseResult, ParsedSymbol


class AppSettingsParser(BaseParser):
    """Parser for appsettings.json configuration files."""
    
    def __init__(self):
        self.language = LanguageEnum.CSHARP
    
    def get_language(self) -> LanguageEnum:
        """Return the language this parser handles."""
        return self.language
    
    def is_supported(self, file_path: Path) -> bool:
        """Check if file is appsettings.json."""
        name = file_path.name.lower()
        return name.startswith('appsettings') and name.endswith('.json')
    
    def parse(self, code: str, file_path: Optional[str] = None) -> ParseResult:
        """
        Parse appsettings.json and extract configuration keys.
        
        Flattens nested configuration into hierarchical keys like:
        Database:ConnectionString
        Logging:LogLevel:Default
        """
        import time
        start_time = time.time()
        
        symbols = []
        errors = []
        
        try:
            # Parse JSON
            data = json.loads(code)
            
            # Determine environment from filename
            environment = self._extract_environment(file_path)
            
            # Flatten and extract configuration entries
            symbols.extend(self._extract_config_entries(data, environment, file_path))
            
        except json.JSONDecodeError as e:
            errors.append(f"JSON parsing error: {str(e)}")
        except Exception as e:
            errors.append(f"AppSettings parsing error: {str(e)}")
        
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
    
    def _extract_environment(self, file_path: Optional[str]) -> str:
        """Extract environment from filename."""
        if not file_path:
            return "default"
        
        filename = Path(file_path).stem.lower()
        
        # appsettings.Development.json -> development
        # appsettings.Production.json -> production
        if 'development' in filename:
            return 'development'
        elif 'production' in filename:
            return 'production'
        elif 'staging' in filename:
            return 'staging'
        elif 'test' in filename:
            return 'test'
        else:
            return 'default'
    
    def _extract_config_entries(
        self,
        data: dict,
        environment: str,
        file_path: Optional[str],
        prefix: str = ""
    ) -> List[ParsedSymbol]:
        """Recursively extract configuration entries with flattened keys."""
        symbols = []
        
        for key, value in data.items():
            # Build hierarchical key
            full_key = f"{prefix}:{key}" if prefix else key
            
            if isinstance(value, dict):
                # Recurse into nested configuration
                symbols.extend(self._extract_config_entries(
                    value,
                    environment,
                    file_path,
                    prefix=full_key
                ))
            else:
                # Leaf configuration value
                value_type = self._get_value_type(value)
                value_str = str(value)
                
                # Check if it's likely a secret
                is_secret = self._is_likely_secret(full_key, value_str)
                
                # Create symbol for this config entry
                symbols.append(ParsedSymbol(
                    kind=SymbolKindEnum.CONSTANT,  # Using CONSTANT for config values
                    name=full_key,
                    start_line=0,
                    end_line=0,
                    start_column=0,
                    end_column=0,
                    signature=f"{full_key}: {value_type}",
                    documentation=f"Configuration value{' (⚠️ secret)' if is_secret else ''}: {value_str[:50]}{'...' if len(value_str) > 50 else ''}",
                    structured_docs={
                        'type': 'configuration',
                        'config_key': full_key,
                        'value': value if not is_secret else '[REDACTED]',
                        'value_type': value_type,
                        'environment': environment,
                        'is_secret': is_secret
                    }
                ))
        
        return symbols
    
    def _get_value_type(self, value: Any) -> str:
        """Get the type of configuration value."""
        if isinstance(value, bool):
            return 'boolean'
        elif isinstance(value, int):
            return 'number'
        elif isinstance(value, float):
            return 'number'
        elif isinstance(value, str):
            return 'string'
        elif isinstance(value, list):
            return 'array'
        elif value is None:
            return 'null'
        else:
            return 'object'
    
    def _is_likely_secret(self, key: str, value: str) -> bool:
        """Check if a configuration key/value is likely a secret."""
        key_lower = key.lower()
        
        # Common secret keywords
        secret_keywords = [
            'password', 'secret', 'key', 'token', 'apikey', 'api_key',
            'connectionstring', 'connection_string', 'credential',
            'auth', 'private', 'certificate', 'salt'
        ]
        
        # Check if any secret keyword is in the key
        for keyword in secret_keywords:
            if keyword in key_lower:
                return True
        
        # Check value patterns (e.g., looks like a JWT, API key, etc.)
        if value and isinstance(value, str):
            value_lower = value.lower()
            # Very long strings might be secrets
            if len(value) > 50 and not value_lower.startswith('http'):
                return True
        
        return False

