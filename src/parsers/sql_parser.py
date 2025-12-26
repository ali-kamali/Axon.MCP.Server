"""SQL parser for migration files and stored procedures."""

import re
from typing import List, Optional, Dict, Any
from pathlib import Path
from dataclasses import dataclass

from src.config.enums import LanguageEnum, SymbolKindEnum
from src.parsers.base_parser import BaseParser, ParseResult, ParsedSymbol


@dataclass
class TableDefinition:
    """Represents a table definition."""
    name: str
    columns: List[Dict[str, str]]
    constraints: List[str]
    indexes: List[str]


@dataclass
class StoredProcedure:
    """Represents a stored procedure."""
    name: str
    parameters: List[Dict[str, str]]
    returns: Optional[str]
    body: str


class SQLParser(BaseParser):
    """Parser for SQL files (migrations, stored procedures, etc.)."""
    
    def __init__(self):
        self.language = LanguageEnum.SQL
    
    def get_language(self) -> LanguageEnum:
        """Return the language this parser handles."""
        return self.language
    
    def is_supported(self, file_path: Path) -> bool:
        """Check if file is a SQL file."""
        return file_path.suffix.lower() in ['.sql', '.ddl']
    
    def parse(self, code: str, file_path: Optional[str] = None) -> ParseResult:
        """
        Parse SQL file and extract structures.
        
        Extracts:
        - CREATE TABLE statements
        - CREATE INDEX statements
        - CREATE PROCEDURE/FUNCTION statements
        - ALTER TABLE statements
        """
        import time
        start_time = time.time()
        
        symbols = []
        errors = []
        
        try:
            # Extract table definitions
            tables = self._extract_tables(code)
            for table in tables:
                symbols.append(self._table_to_symbol(table, file_path))
            
            # Extract stored procedures
            procedures = self._extract_procedures(code)
            for proc in procedures:
                symbols.append(self._procedure_to_symbol(proc, file_path))
            
            # Extract views
            views = self._extract_views(code)
            for view in views:
                symbols.append(self._view_to_symbol(view, file_path))
            
        except Exception as e:
            errors.append(f"SQL parsing error: {str(e)}")
        
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
    
    def _extract_tables(self, code: str) -> List[TableDefinition]:
        """Extract CREATE TABLE statements."""
        tables = []
        
        # Match CREATE TABLE statements
        table_pattern = r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\((.*?)\);'
        matches = re.finditer(table_pattern, code, re.IGNORECASE | re.DOTALL)
        
        for match in matches:
            table_name = match.group(1)
            table_body = match.group(2)
            
            # Parse columns and constraints
            columns = self._parse_columns(table_body)
            constraints = self._parse_constraints(table_body)
            
            tables.append(TableDefinition(
                name=table_name,
                columns=columns,
                constraints=constraints,
                indexes=[]
            ))
        
        return tables
    
    def _parse_columns(self, table_body: str) -> List[Dict[str, str]]:
        """Parse column definitions."""
        columns = []
        
        # Split by comma (simplified - doesn't handle nested commas)
        lines = table_body.split(',')
        
        for line in lines:
            line = line.strip()
            
            # Skip constraints
            if any(kw in line.upper() for kw in ['PRIMARY KEY', 'FOREIGN KEY', 'CONSTRAINT', 'INDEX']):
                continue
            
            # Parse column definition
            parts = line.split()
            if len(parts) >= 2:
                col_name = parts[0].strip('`"\'')
                col_type = parts[1]
                
                # Extract additional properties
                nullable = 'NOT NULL' not in line.upper()
                has_default = 'DEFAULT' in line.upper()
                
                columns.append({
                    'name': col_name,
                    'type': col_type,
                    'nullable': nullable,
                    'has_default': has_default
                })
        
        return columns
    
    def _parse_constraints(self, table_body: str) -> List[str]:
        """Parse table constraints."""
        constraints = []
        
        constraint_keywords = ['PRIMARY KEY', 'FOREIGN KEY', 'UNIQUE', 'CHECK']
        
        for line in table_body.split(','):
            line_upper = line.strip().upper()
            for keyword in constraint_keywords:
                if keyword in line_upper:
                    constraints.append(line.strip())
                    break
        
        return constraints
    
    def _extract_procedures(self, code: str) -> List[StoredProcedure]:
        """Extract CREATE PROCEDURE/FUNCTION statements."""
        procedures = []
        
        # Match CREATE PROCEDURE
        proc_pattern = r'CREATE\s+(?:OR\s+REPLACE\s+)?(?:PROCEDURE|FUNCTION)\s+(\w+)\s*\((.*?)\)(.*?)(?:BEGIN|AS)(.*?)END;'
        matches = re.finditer(proc_pattern, code, re.IGNORECASE | re.DOTALL)
        
        for match in matches:
            proc_name = match.group(1)
            params = match.group(2)
            returns = match.group(3).strip() if match.group(3) else None
            body = match.group(4)
            
            # Parse parameters
            parameters = self._parse_procedure_params(params)
            
            procedures.append(StoredProcedure(
                name=proc_name,
                parameters=parameters,
                returns=returns if 'RETURNS' in str(returns).upper() else None,
                body=body.strip()
            ))
        
        return procedures
    
    def _parse_procedure_params(self, params_str: str) -> List[Dict[str, str]]:
        """Parse procedure parameters."""
        parameters = []
        
        if not params_str.strip():
            return parameters
        
        # Split by comma
        params = params_str.split(',')
        
        for param in params:
            param = param.strip()
            parts = param.split()
            
            if len(parts) >= 2:
                # Handle IN/OUT/INOUT prefix
                direction = 'IN'
                if parts[0].upper() in ['IN', 'OUT', 'INOUT']:
                    direction = parts[0].upper()
                    parts = parts[1:]
                
                param_name = parts[0].strip('@')
                param_type = parts[1] if len(parts) > 1 else 'unknown'
                
                parameters.append({
                    'name': param_name,
                    'type': param_type,
                    'direction': direction
                })
        
        return parameters
    
    def _extract_views(self, code: str) -> List[Dict[str, Any]]:
        """Extract CREATE VIEW statements."""
        views = []
        
        view_pattern = r'CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(\w+)\s+AS\s+(.*?)(?:;|$)'
        matches = re.finditer(view_pattern, code, re.IGNORECASE | re.DOTALL)
        
        for match in matches:
            view_name = match.group(1)
            query = match.group(2).strip()
            
            views.append({
                'name': view_name,
                'query': query
            })
        
        return views
    
    def _table_to_symbol(self, table: TableDefinition, file_path: Optional[str]) -> ParsedSymbol:
        """Convert table definition to symbol."""
        # Format documentation
        doc_lines = [f"Table with {len(table.columns)} columns"]
        
        if table.columns:
            doc_lines.append("\nColumns:")
            for col in table.columns[:10]:  # Limit to first 10
                doc_lines.append(f"  - {col['name']}: {col['type']}")
        
        if table.constraints:
            doc_lines.append(f"\nConstraints: {len(table.constraints)}")
        
        return ParsedSymbol(
            kind=SymbolKindEnum.CLASS,  # Use CLASS for tables
            name=table.name,
            start_line=0,
            end_line=0,
            start_column=0,
            end_column=0,
            signature=f"CREATE TABLE {table.name}",
            documentation='\n'.join(doc_lines),
            structured_docs={
                'type': 'database_table',
                'columns': table.columns,
                'constraints': table.constraints
            }
        )
    
    def _procedure_to_symbol(self, proc: StoredProcedure, file_path: Optional[str]) -> ParsedSymbol:
        """Convert stored procedure to symbol."""
        # Format documentation
        doc_lines = [f"Stored procedure with {len(proc.parameters)} parameters"]
        
        if proc.parameters:
            doc_lines.append("\nParameters:")
            for param in proc.parameters:
                doc_lines.append(f"  - {param['name']}: {param['type']} ({param['direction']})")
        
        if proc.returns:
            doc_lines.append(f"\nReturns: {proc.returns}")
        
        return ParsedSymbol(
            kind=SymbolKindEnum.FUNCTION,  # Use FUNCTION for procedures
            name=proc.name,
            start_line=0,
            end_line=0,
            start_column=0,
            end_column=0,
            signature=f"CREATE PROCEDURE {proc.name}",
            documentation='\n'.join(doc_lines),
            structured_docs={
                'type': 'stored_procedure',
                'parameters': proc.parameters,
                'returns': proc.returns,
                'body_preview': proc.body[:200]
            },
            parameters=proc.parameters
        )
    
    def _view_to_symbol(self, view: Dict[str, Any], file_path: Optional[str]) -> ParsedSymbol:
        """Convert view to symbol."""
        return ParsedSymbol(
            kind=SymbolKindEnum.CLASS,  # Use CLASS for views
            name=view['name'],
            start_line=0,
            end_line=0,
            start_column=0,
            end_column=0,
            signature=f"CREATE VIEW {view['name']}",
            documentation=f"Database view\n\nQuery:\n{view['query'][:200]}",
            structured_docs={
                'type': 'database_view',
                'query': view['query']
            }
        )

