"""Call target resolution for building accurate call graphs."""

from typing import Optional, List, Dict, Any
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Symbol, File, Relation
from src.config.enums import SymbolKindEnum, RelationTypeEnum, LanguageEnum
from datetime import datetime
from src.extractors.call_analyzer import Call
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


from src.parsers.roslyn_integration import RoslynAnalyzer

class CallResolver:
    """Resolves function/method calls to actual symbol IDs."""
    
    def __init__(self, session: AsyncSession, roslyn_analyzer: Optional[RoslynAnalyzer] = None):
        """
        Initialize call resolver.
        
        Args:
            session: Database session
            roslyn_analyzer: Optional Roslyn analyzer for fallback resolution
        """
        self.session = session
        self.roslyn_analyzer = roslyn_analyzer
    
    async def resolve_call_target(
        self,
        call: Call,
        calling_symbol: Symbol,
        file: File,
        imports: Optional[List[str]] = None,
        field_types: Optional[Dict[str, str]] = None,
        code: Optional[str] = None
    ) -> Optional[int]:
        """
        Resolve a call to the actual symbol ID.
        
        Strategy:
        1. Check local file first (same class methods)
        2. Check imported symbols
        3. Check base class methods (inheritance)
        4. Check field/variable types (dependency injection)
        5. Fuzzy match by name if exact match fails
        
        Args:
            call: Call information
            calling_symbol: Symbol making the call
            file: File containing the calling symbol
            imports: List of imported namespaces/modules
            field_types: Mapping of variable names to their types (e.g., _service -> IUserService)
            
        Returns:
            Symbol ID of the call target, or None if not found
        """
        if imports is None:
            imports = []
        if field_types is None:
            field_types = {}

        # DEBUG: Log the call being resolved
        logger.debug(
            "resolving_call",
            method=call.method_name,
            receiver=call.receiver,
            caller=calling_symbol.name,
            parent=calling_symbol.parent_name
        )

        # Strategy 0: Resolve receiver type if it's a field/variable
        receiver_type = None
        if call.receiver and call.receiver in field_types:
            receiver_type = field_types[call.receiver]
            logger.debug("resolved_receiver_type", receiver=call.receiver, type=receiver_type)
        
        # Strategy 1: Local methods in same file
        if not call.receiver or call.receiver in ['this', 'base']:
            target = await self._find_local_method(
                call.method_name,
                file.id,
                calling_symbol.parent_name
            )
            if target:
                logger.debug("resolved_local", method=call.method_name, target_id=target.id)
                return target.id
        
        # Strategy 2: Methods in parent class (for 'this' calls)
        if calling_symbol.parent_name:
            target = await self._find_in_parent_class(
                call.method_name,
                calling_symbol.parent_name,
                file.repository_id
            )
            if target:
                logger.debug("resolved_parent_class", method=call.method_name, target_id=target.id)
                return target.id
        
        # Strategy 3: Static or qualified calls (including resolved fields)
        if call.receiver or receiver_type:
            # If we resolved the receiver to a type (e.g. _service -> IUserService), use that
            target_class_name = receiver_type if receiver_type else call.receiver
            
            # Try to find the class/interface
            target = await self._find_qualified_call(
                call.method_name,
                target_class_name,
                file.repository_id,
                imports
            )
            if target:
                logger.debug("resolved_qualified", method=call.method_name, target_id=target.id)
                return target.id
        
        # Strategy 4: Fuzzy match by name across repository
        target = await self._fuzzy_match_by_name(
            call.method_name,
            file.repository_id
        )
        if target:
            logger.debug("resolved_fuzzy", method=call.method_name, target_id=target.id)
            return target.id
            
        # Strategy 5: Roslyn Fallback (External DLLs)
        if self.roslyn_analyzer and code:
            target_id = await self._resolve_with_roslyn(
                call.method_name,
                code,
                file.path,
                call.line_number,
                call.start_column,
                file.repository_id
            )
            if target_id:
                logger.debug("resolved_via_roslyn", method=call.method_name, target_id=target_id)
                return target_id
        
        # DEBUG: Log unresolved call
        logger.debug(
            "call_not_resolved",
            method=call.method_name,
            receiver=call.receiver,
            caller=calling_symbol.name
        )
        
        return None
    
        return None

    async def resolve_usage_target(
        self,
        name: str,
        calling_symbol: Symbol,
        file: File,
        imports: Optional[List[str]] = None,
        receiver: Optional[str] = None,
        field_types: Optional[Dict[str, str]] = None
    ) -> Optional[int]:
        """
        Resolve a variable/property usage to actual symbol ID.
        
        Args:
            name: Name of variable/property used
            calling_symbol: Symbol using the variable
            file: File containing the usage
            imports: List of imported namespaces
            receiver: Receiver object (e.g., "user" in "user.Name")
            field_types: Map of variable names to types
            
        Returns:
            Symbol ID of the target, or None
        """
        if imports is None:
            imports = []
        if field_types is None:
            field_types = {}
            
        # Strategy 0: Resolve receiver type if present
        receiver_type = None
        if receiver and receiver in field_types:
            receiver_type = field_types[receiver]
            
        # Strategy 1: Property/Field in same class (if no receiver or receiver is this)
        if (not receiver or receiver == 'this') and calling_symbol.parent_name:
            target = await self._find_member_in_class(
                name,
                calling_symbol.parent_name,
                file.repository_id
            )
            if target:
                return target.id
        
        # Strategy 2: Instance property on another object
        if receiver_type:
            # We know the type of the receiver (e.g. Test.User), look for property 'name' in that type
            target = await self._find_qualified_member(
                name,
                receiver_type, # This is the class name
                file.repository_id,
                imports
            )
            if target:
                return target.id

        # Strategy 3: Static property/field in other classes (if name is Class.Prop)
        # Or if receiver looks like a class name (PascalCase)
        if '.' in name:
            parts = name.split('.')
            class_name = '.'.join(parts[:-1])
            member_name = parts[-1]
            
            target = await self._find_qualified_member(
                member_name,
                class_name,
                file.repository_id,
                imports
            )
            if target:
                return target.id
        elif receiver and receiver[0].isupper():
            # Receiver might be a class name (Static access like User.Count)
            target = await self._find_qualified_member(
                name,
                receiver,
                file.repository_id,
                imports
            )
            if target:
                return target.id
        
        return None

        return None

    async def resolve_type(
        self,
        type_name: str,
        file: File,
        imports: Optional[List[str]] = None
    ) -> Optional[int]:
        """
        Resolve a type name to a symbol ID.
        
        Args:
            type_name: Name of the type (e.g. "User", "List<string>")
            file: File context
            imports: List of imports
            
        Returns:
            Symbol ID or None
        """
        if imports is None:
            imports = []
            
        # Handle generic types: List<User> -> List
        if '<' in type_name:
            type_name = type_name.split('<')[0]
            
        # Handle array types: User[] -> User
        if '[' in type_name:
            type_name = type_name.split('[')[0]
            
        # Potential FQNs
        potential_fqns = [type_name]
        for imp in imports:
            if imp:
                potential_fqns.append(f"{imp}.{type_name}")
                
        # Query for CLASS, INTERFACE, STRUCT, ENUM
        result = await self.session.execute(
            select(Symbol)
            .join(File, Symbol.file_id == File.id)
            .where(
                File.repository_id == file.repository_id,
                Symbol.fully_qualified_name.in_(potential_fqns),
                Symbol.kind.in_([
                    SymbolKindEnum.CLASS, 
                    SymbolKindEnum.INTERFACE, 
                    SymbolKindEnum.STRUCT, 
                    SymbolKindEnum.ENUM
                ])
            )
        )
        symbols = result.scalars().all()
        
        if symbols:
            # Prefer exact match if multiple (though FQN match should be unique per FQN)
            # If we have multiple matches (e.g. same name in different namespaces but both imported?), 
            # we might need better logic. For now, take the first one.
            return symbols[0].id
            
        # Fallback: Try simple name match if unique
        result = await self.session.execute(
            select(Symbol)
            .join(File, Symbol.file_id == File.id)
            .where(
                File.repository_id == file.repository_id,
                Symbol.name == type_name,
                Symbol.kind.in_([
                    SymbolKindEnum.CLASS, 
                    SymbolKindEnum.INTERFACE, 
                    SymbolKindEnum.STRUCT, 
                    SymbolKindEnum.ENUM
                ])
            )
        )
        symbols = result.scalars().all()
        
        if len(symbols) == 1:
            return symbols[0].id
            
        return None

    async def _find_member_in_class(
        self,
        member_name: str,
        class_fqn: str,
        repository_id: int
    ) -> Optional[Symbol]:
        """Find property/field in a class."""
        # Get class symbol
        result = await self.session.execute(
            select(Symbol)
            .join(File, Symbol.file_id == File.id)
            .where(
                File.repository_id == repository_id,
                Symbol.fully_qualified_name == class_fqn,
                Symbol.kind == SymbolKindEnum.CLASS
            )
            .limit(1)
        )
        class_symbol = result.scalar_one_or_none()
        
        if not class_symbol:
            return None
            
        # Find member
        result = await self.session.execute(
            select(Symbol)
            .where(
                Symbol.parent_name == class_symbol.fully_qualified_name,
                Symbol.name == member_name,
                Symbol.kind.in_([SymbolKindEnum.PROPERTY, SymbolKindEnum.VARIABLE, SymbolKindEnum.CONSTANT])
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _find_qualified_member(
        self,
        member_name: str,
        class_name: str,
        repository_id: int,
        imports: List[str]
    ) -> Optional[Symbol]:
        """Find static member in another class."""
        # Similar to _find_qualified_call but for properties
        potential_fqns = [class_name]
        for imp in imports:
            if imp:
                potential_fqns.append(f"{imp}.{class_name}")
                
        result = await self.session.execute(
            select(Symbol)
            .join(File, Symbol.file_id == File.id)
            .where(
                File.repository_id == repository_id,
                Symbol.fully_qualified_name.in_(potential_fqns),
                Symbol.kind.in_([SymbolKindEnum.CLASS, SymbolKindEnum.INTERFACE])
            )
        )
        class_symbols = result.scalars().all()
        
        for class_symbol in class_symbols:
            result = await self.session.execute(
                select(Symbol)
                .where(
                    Symbol.parent_name == class_symbol.fully_qualified_name,
                    Symbol.name == member_name,
                    Symbol.kind.in_([SymbolKindEnum.PROPERTY, SymbolKindEnum.VARIABLE, SymbolKindEnum.CONSTANT])
                )
                .limit(1)
            )
            target = result.scalar_one_or_none()
            if target:
                return target
                
        return None
    
    async def _find_local_method(
        self,
        method_name: str,
        file_id: int,
        parent_class: Optional[str]
    ) -> Optional[Symbol]:
        """Find method in the same file."""
        filters = [
            Symbol.file_id == file_id,
            Symbol.name == method_name,
            Symbol.kind.in_([SymbolKindEnum.METHOD, SymbolKindEnum.FUNCTION])
        ]
        
        if parent_class:
            filters.append(Symbol.parent_name == parent_class)
        
        result = await self.session.execute(
            select(Symbol).where(*filters).limit(1)
        )
        return result.scalar_one_or_none()
    
    async def _find_in_parent_class(
        self,
        method_name: str,
        parent_class_fqn: str,
        repository_id: int
    ) -> Optional[Symbol]:
        """Find method in parent class."""
        # First, get the parent class symbol
        result = await self.session.execute(
            select(Symbol, File)
            .join(File, Symbol.file_id == File.id)
            .where(
                File.repository_id == repository_id,
                Symbol.fully_qualified_name == parent_class_fqn,
                Symbol.kind == SymbolKindEnum.CLASS
            )
            .limit(1)
        )
        parent_row = result.first()
        
        if not parent_row:
            return None
        
        parent_class, _ = parent_row
        
        # Find method in this class
        result = await self.session.execute(
            select(Symbol)
            .where(
                Symbol.parent_name == parent_class.fully_qualified_name,
                Symbol.name == method_name,
                Symbol.kind == SymbolKindEnum.METHOD
            )
            .limit(1)
        )
        return result.scalar_one_or_none()
    
    async def _find_qualified_call(
        self,
        method_name: str,
        receiver: str,
        repository_id: int,
        imports: List[str] = None
    ) -> Optional[Symbol]:
        """
        Find method by qualified name.
        
        For calls like: UserService.GetUser() or obj.GetValue()
        """
        if imports is None:
            imports = []
            
        # Potential fully qualified names for the class
        potential_fqns = [receiver]
        
        # Add combinations with imports
        for imp in imports:
            if imp:
                potential_fqns.append(f"{imp}.{receiver}")
        
        # Try to find class matching receiver
        # We search for any class/interface that matches one of the potential FQNs
        # or just the name if it's unique enough
        
        # 1. Try exact match on Fully Qualified Name first (most accurate)
        result = await self.session.execute(
            select(Symbol)
            .join(File, Symbol.file_id == File.id)
            .where(
                File.repository_id == repository_id,
                Symbol.fully_qualified_name.in_(potential_fqns),
                Symbol.kind.in_([SymbolKindEnum.CLASS, SymbolKindEnum.INTERFACE])
            )
        )
        class_symbols = result.scalars().all()
        
        # 2. If no exact FQN match, try simple name match
        if not class_symbols:
            result = await self.session.execute(
                select(Symbol)
                .join(File, Symbol.file_id == File.id)
                .where(
                    File.repository_id == repository_id,
                    Symbol.name == receiver,
                    Symbol.kind.in_([SymbolKindEnum.CLASS, SymbolKindEnum.INTERFACE])
                )
            )
            class_symbols = result.scalars().all()
        
        if not class_symbols:
            return None
            
        # For each candidate class, look for the method
        for class_symbol in class_symbols:
            # Find method in this class
            result = await self.session.execute(
                select(Symbol)
                .where(
                    Symbol.parent_name == class_symbol.fully_qualified_name,
                    Symbol.name == method_name,
                    Symbol.kind == SymbolKindEnum.METHOD
                )
                .limit(1)
            )
            method_symbol = result.scalar_one_or_none()
            if method_symbol:
                return method_symbol
                
        return None
    
    async def _fuzzy_match_by_name(
        self,
        method_name: str,
        repository_id: int
    ) -> Optional[Symbol]:
        """
        Fuzzy match by name across repository.
        
        Falls back to finding any method with matching name.
        """
        result = await self.session.execute(
            select(Symbol, File)
            .join(File, Symbol.file_id == File.id)
            .where(
                File.repository_id == repository_id,
                Symbol.name == method_name,
                Symbol.kind.in_([SymbolKindEnum.METHOD, SymbolKindEnum.FUNCTION])
            )
            .limit(1)  # Take first match
        )
        row = result.first()
        return row[0] if row else None

    async def _resolve_with_roslyn(
        self,
        method_name: str,
        code: str,
        file_path: str,
        line: int,
        column: int,
        repository_id: int
    ) -> Optional[int]:
        """Resolve using Roslyn analyzer."""
        if not self.roslyn_analyzer or not self.roslyn_analyzer.is_available():
            return None
            
        # Calculate offset
        try:
            lines = code.split('\n')
            if line > len(lines):
                return None
            # Simple offset calculation
            offset = sum(len(l) + 1 for l in lines[:line-1]) + column
        except Exception:
            return None

        # Call Roslyn
        symbol_info = await self.roslyn_analyzer.resolve_reference(
            code,
            file_path,
            offset
        )
        
        if not symbol_info:
            return None
            
        fqn = symbol_info.get("fully_qualified_name")
        is_external = symbol_info.get("is_external", False)
        assembly_name = symbol_info.get("assembly_name")
        
        if not fqn:
            return None
            
        # Check if symbol exists in DB
        result = await self.session.execute(
            select(Symbol).where(Symbol.fully_qualified_name == fqn).limit(1)
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            return existing.id
            
        if is_external and assembly_name:
            # Create synthetic external symbol
            return await self._get_or_create_external_symbol(symbol_info, assembly_name, repository_id)
            
        return None

    async def _get_or_create_external_symbol(
        self,
        symbol_info: Dict[str, Any],
        assembly_name: str,
        repository_id: int
    ) -> int:
        """Create a synthetic symbol for an external library reference."""
        fqn = symbol_info["fully_qualified_name"]
        
        # Double check existence to avoid race conditions
        result = await self.session.execute(
            select(Symbol).where(Symbol.fully_qualified_name == fqn).limit(1)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing.id

        # Needed: A dummy file for this assembly to satisfy foreign key
        # We'll treat the assembly name as a "path"
        external_file_path = f"[External] {assembly_name}"
        
        # Check if "file" exists
        result = await self.session.execute(
            select(File).where(
                File.repository_id == repository_id,
                File.path == external_file_path
            ).limit(1)
        )
        external_file = result.scalar_one_or_none()
        
        if not external_file:
            # Create dummy file
            external_file = File(
                repository_id=repository_id,
                path=external_file_path,
                language=LanguageEnum.CSHARP,
                size_bytes=0,
                line_count=0,
                content_hash="external",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            self.session.add(external_file)
            await self.session.flush() # flush to get ID
            
        # Map Kind string to Enum
        kind_str = symbol_info.get("kind", "Method")
        kind_enum = SymbolKindEnum.METHOD
        try:
            # Handle Roslyn kinds like "NamedType" -> CLASS
            if kind_str == "NamedType":
                kind_enum = SymbolKindEnum.CLASS
            else:
                kind_enum = SymbolKindEnum(kind_str)
        except ValueError:
            pass # Default to METHOD if unknown
            
        # Create Symbol
        new_symbol = Symbol(
            file_id=external_file.id,
            language=LanguageEnum.CSHARP,
            kind=kind_enum,
            name=symbol_info.get("name", fqn.split('.')[-1]),
            fully_qualified_name=fqn,
            start_line=0,
            end_line=0,
            assembly_name=assembly_name,
            is_generated=1 # Mark as generated/synthetic
        )
        
        self.session.add(new_symbol)
        await self.session.commit()
        
        return new_symbol.id

