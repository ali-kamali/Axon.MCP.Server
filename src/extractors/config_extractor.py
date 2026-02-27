import json
import re
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models import ConfigurationEntry, File
from src.utils.logging_config import get_logger
from src.utils.async_compat import maybe_await

logger = get_logger(__name__)

class ConfigExtractor:
    """Extracts configuration entries from various file formats."""
    
    def __init__(self, session: AsyncSession):
        self.session = session

    async def extract_configuration(self, repository_id: int, repo_path: Path) -> int:
        """
        Extract configuration from all config files in the repository.
        
        Args:
            repository_id: Repository ID
            repo_path: Path to the cloned repository
            
        Returns:
            Number of configuration entries extracted
        """
        from sqlalchemy import select, delete
        
        # 1. Delete existing configuration entries for this repository
        await self.session.execute(
            delete(ConfigurationEntry).where(ConfigurationEntry.repository_id == repository_id)
        )
        
        # 2. Find all potential config files
        # We look for .json, .config, .xml files
        # And filter by name (appsettings*, web.config, *.config)
        stmt = select(File).where(
            File.repository_id == repository_id,
            (File.path.ilike('%.json')) | (File.path.ilike('%.config')) | (File.path.ilike('%.xml'))
        )
        result = await self.session.execute(stmt)
        files = result.scalars().all()
        
        entries_count = 0
        
        for file in files:
            filename = Path(file.path).name.lower()
            
            # Filter for relevant config files
            is_config = False
            if filename.startswith('appsettings') and filename.endswith('.json'):
                is_config = True
            elif filename == 'web.config' or filename.endswith('.config'):
                is_config = True
            elif filename.endswith('.xml') and ('config' in filename or 'settings' in filename):
                is_config = True
                
            if not is_config:
                continue
                
            try:
                # Construct absolute path
                # file.path is relative to repo root
                file_abs_path = repo_path / file.path
                
                if not file_abs_path.exists():
                    logger.warning(f"Config file not found on disk: {file_abs_path}")
                    continue
                    
                # Read content
                content = file_abs_path.read_text(encoding='utf-8-sig', errors='ignore')
                
                # Extract configs
                entries = self.extract_configs(file, content)
                
                for entry in entries:
                    await maybe_await(self.session.add(entry))
                    entries_count += 1
                    
            except Exception as e:
                logger.error(f"Failed to process config file {file.path}: {e}")
                
        return entries_count

    def extract_configs(self, file: File, content: str) -> List[ConfigurationEntry]:
        """
        Extract configuration entries from a file.
        
        Args:
            file: File object
            content: File content string
            
        Returns:
            List of ConfigurationEntry objects (not yet persisted)
        """
        entries = []
        file_path = Path(file.path)
        filename = file_path.name.lower()
        
        # Determine environment from filename (e.g., appsettings.Development.json)
        environment = "default"
        parts = filename.split('.')
        if len(parts) > 2 and parts[-1] == 'json':
            # Check for environment segment
            potential_env = parts[-2].lower()
            if potential_env not in ['appsettings', 'json']:
                environment = potential_env
        
        try:
            if filename.endswith('.json'):
                entries = self._parse_json(content, file, environment)
            elif filename.endswith('.config') or filename.endswith('.xml'):
                entries = self._parse_xml(content, file, environment)
        except Exception as e:
            logger.error(f"Failed to parse config file {file.path}: {e}")
            
        return entries

    def _parse_json(self, content: str, file: File, environment: str) -> List[ConfigurationEntry]:
        """Parse JSON configuration (flattened). Supports JSON with comments (JSONC)."""
        entries = []
        try:
            # Try standard JSON first
            data = json.loads(content)
            flattened = self._flatten_json(data)
            
            for key, value in flattened.items():
                # Determine type
                config_type = "string"
                if isinstance(value, bool):
                    config_type = "boolean"
                elif isinstance(value, (int, float)):
                    config_type = "number"
                elif value is None:
                    config_type = "null"
                
                # Check if secret
                is_secret = 0
                if any(secret_term in key.lower() for secret_term in ['password', 'secret', 'key', 'token', 'credential', 'connectionstring']):
                    is_secret = 1
                    # Mask value if secret
                    value = "***"
                
                # Convert value to string, handling booleans specially to use lowercase
                if isinstance(value, bool):
                    config_value_str = str(value).lower()
                elif value is not None:
                    config_value_str = str(value)
                else:
                    config_value_str = None
                    
                entry = ConfigurationEntry(
                    repository_id=file.repository_id,
                    file_id=file.id,
                    config_key=key,
                    config_value=config_value_str,
                    config_type=config_type,
                    environment=environment,
                    is_secret=is_secret,
                    file_path=file.path
                )
                entries.append(entry)
                
        except json.JSONDecodeError as e:
            # Standard JSON failed - try to clean comments and retry
            try:
                cleaned_content = self._strip_json_comments(content)
                data = json.loads(cleaned_content)
                flattened = self._flatten_json(data)
                
                for key, value in flattened.items():
                    config_type = "string"
                    if isinstance(value, bool):
                        config_type = "boolean"
                    elif isinstance(value, (int, float)):
                        config_type = "number"
                    elif value is None:
                        config_type = "null"
                    
                    is_secret = 0
                    if any(secret_term in key.lower() for secret_term in ['password', 'secret', 'key', 'token', 'credential', 'connectionstring']):
                        is_secret = 1
                        value = "***"
                    
                    # Convert value to string, handling booleans specially to use lowercase
                    if isinstance(value, bool):
                        config_value_str = str(value).lower()
                    elif value is not None:
                        config_value_str = str(value)
                    else:
                        config_value_str = None
                        
                    entry = ConfigurationEntry(
                        repository_id=file.repository_id,
                        file_id=file.id,
                        config_key=key,
                        config_value=config_value_str,
                        config_type=config_type,
                        environment=environment,
                        is_secret=is_secret,
                        file_path=file.path
                    )
                    entries.append(entry)
                
                logger.info(f"Successfully parsed {file.path} after stripping comments")
                
            except json.JSONDecodeError as e2:
                # Even after cleaning, JSON is invalid
                logger.warning(
                    f"Invalid JSON in {file.path} at line {e2.lineno}, column {e2.colno}: {e2.msg}. "
                    f"Skipping configuration extraction."
                )
            
        return entries

    def _strip_json_comments(self, content: str) -> str:
        """
        Strip single-line (//) and multi-line (/* */) comments from JSON.
        Also removes trailing commas before closing brackets/braces.
        
        This allows parsing of JSONC (JSON with Comments) used in VS Code and many
        .NET configuration files.
        """
        
        # Remove single-line comments (// ...)
        # Must be careful not to remove // inside strings
        lines = content.split('\n')
        cleaned_lines = []
        in_string = False
        in_multiline_comment = False
        
        for line in lines:
            cleaned_line = []
            i = 0
            while i < len(line):
                char = line[i]
                
                # Handle multi-line comments
                if not in_string and i < len(line) - 1:
                    two_char = line[i:i+2]
                    if two_char == '/*':
                        in_multiline_comment = True
                        i += 2
                        continue
                    elif two_char == '*/' and in_multiline_comment:
                        in_multiline_comment = False
                        i += 2
                        continue
                    elif two_char == '//' and not in_multiline_comment:
                        # Rest of line is comment
                        break
                
                # Track if we're inside a string
                if char == '"' and (i == 0 or line[i-1] != '\\'):
                    in_string = not in_string
                
                # Add character if not in comment
                if not in_multiline_comment:
                    cleaned_line.append(char)
                
                i += 1
            
            cleaned_lines.append(''.join(cleaned_line))
        
        result = '\n'.join(cleaned_lines)
        
        # Remove trailing commas before } or ]
        result = re.sub(r',\s*([}\]])', r'\1', result)
        
        return result

    def _flatten_json(self, y: Any, parent_key: str = '', sep: str = ':') -> Dict[str, Any]:
        """Flatten nested JSON into Key:SubKey format."""
        items: Dict[str, Any] = {}
        
        if isinstance(y, dict):
            for k, v in y.items():
                new_key = f"{parent_key}{sep}{k}" if parent_key else k
                if isinstance(v, (dict, list)):
                    items.update(self._flatten_json(v, new_key, sep=sep))
                else:
                    items[new_key] = v
        elif isinstance(y, list):
            for i, v in enumerate(y):
                new_key = f"{parent_key}{sep}{i}" if parent_key else str(i)
                if isinstance(v, (dict, list)):
                    items.update(self._flatten_json(v, new_key, sep=sep))
                else:
                    items[new_key] = v
        else:
            items[parent_key] = y
            
        return items

    def _parse_xml(self, content: str, file: File, environment: str) -> List[ConfigurationEntry]:
        """Parse XML/Config files (appSettings, connectionStrings)."""
        entries = []
        try:
            root = ET.fromstring(content)
            
            # 1. Parse <appSettings>
            # <add key="KeyName" value="Value" />
            for app_setting in root.findall(".//appSettings/add"):
                key = app_setting.get('key')
                value = app_setting.get('value')
                
                if key:
                    is_secret = 0
                    if any(secret_term in key.lower() for secret_term in ['password', 'secret', 'key', 'token', 'credential']):
                        is_secret = 1
                        value = "***"
                        
                    entries.append(ConfigurationEntry(
                        repository_id=file.repository_id,
                        file_id=file.id,
                        config_key=f"AppSettings:{key}",
                        config_value=value,
                        config_type="string",
                        environment=environment,
                        is_secret=is_secret,
                        file_path=file.path
                    ))

            # 2. Parse <connectionStrings>
            # <add name="DbConnection" connectionString="..." />
            for conn_str in root.findall(".//connectionStrings/add"):
                name = conn_str.get('name')
                value = conn_str.get('connectionString')
                
                if name:
                    entries.append(ConfigurationEntry(
                        repository_id=file.repository_id,
                        file_id=file.id,
                        config_key=f"ConnectionStrings:{name}",
                        config_value="***" if value else None, # Always treat connection strings as secrets
                        config_type="string",
                        environment=environment,
                        is_secret=1,
                        file_path=file.path
                    ))
                    
        except ET.ParseError:
            logger.warning(f"Invalid XML in {file.path}")
            
        return entries
