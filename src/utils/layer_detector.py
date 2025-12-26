"""
Layer detection utility for identifying architectural layers in code.

Detects common architectural patterns like MVC, Clean Architecture, and N-tier.
"""
from typing import Optional
from src.database.models import Symbol, File
from src.config.enums import SymbolKindEnum


class LayerDetector:
    """Detect architectural layer of symbols based on naming and location patterns."""
    
    # Layer constants
    CONTROLLER = "Controller"
    SERVICE = "Service"
    REPOSITORY = "Repository"
    DATABASE = "Database"
    MODEL = "Model"
    MIDDLEWARE = "Middleware"
    UTILITY = "Utility"
    VALIDATOR = "Validator"
    MAPPER = "Mapper"
    UNKNOWN = "Unknown"
    
    # Layer emojis for visual representation
    LAYER_EMOJIS = {
        CONTROLLER: "🎯",
        SERVICE: "⚙️",
        REPOSITORY: "🗄️",
        DATABASE: "💾",
        MODEL: "📦",
        MIDDLEWARE: "🔀",
        UTILITY: "🔧",
        VALIDATOR: "✅",
        MAPPER: "🗺️",
        UNKNOWN: "❓"
    }
    
    @staticmethod
    def detect_layer(symbol: Symbol, file: Optional[File] = None) -> str:
        """
        Detect architectural layer of a symbol.
        
        Args:
            symbol: Symbol to analyze
            file: Optional file information for path-based detection
            
        Returns:
            Layer name (e.g., "Controller", "Service", "Repository")
        """
        if not symbol:
            return LayerDetector.UNKNOWN
        
        name = symbol.name or ""
        parent_name = symbol.parent_name or ""
        file_path = file.path.lower() if file else ""
        
        # Controller detection
        if LayerDetector._is_controller(name, parent_name, file_path, symbol):
            return LayerDetector.CONTROLLER
        
        # Service detection
        if LayerDetector._is_service(name, parent_name, file_path):
            return LayerDetector.SERVICE
        
        # Repository detection
        if LayerDetector._is_repository(name, parent_name, file_path):
            return LayerDetector.REPOSITORY
        
        # Database detection
        if LayerDetector._is_database(name, parent_name, file_path):
            return LayerDetector.DATABASE
        
        # Middleware detection
        if LayerDetector._is_middleware(name, parent_name, file_path):
            return LayerDetector.MIDDLEWARE
        
        # Validator detection
        if LayerDetector._is_validator(name, parent_name, file_path):
            return LayerDetector.VALIDATOR
        
        # Mapper detection
        if LayerDetector._is_mapper(name, parent_name, file_path):
            return LayerDetector.MAPPER
        
        # Model detection
        if LayerDetector._is_model(name, parent_name, file_path, symbol):
            return LayerDetector.MODEL
        
        # Utility detection
        if LayerDetector._is_utility(name, parent_name, file_path):
            return LayerDetector.UTILITY
        
        return LayerDetector.UNKNOWN
    
    @staticmethod
    def get_layer_emoji(layer: str) -> str:
        """Get emoji representation of a layer."""
        return LayerDetector.LAYER_EMOJIS.get(layer, "❓")
    
    @staticmethod
    def _is_controller(name: str, parent_name: str, file_path: str, symbol: Symbol) -> bool:
        """Detect if symbol is a controller."""
        name_lower = name.lower()
        parent_lower = parent_name.lower()
        
        # Name patterns
        if any(pattern in name_lower for pattern in ['controller', 'apicontroller']):
            return True
        
        if any(pattern in parent_lower for pattern in ['controller', 'apicontroller']):
            return True
        
        # Path patterns
        if any(pattern in file_path for pattern in ['controllers/', 'controller/', '/controllers', '/controller']):
            return True
        
        # Attribute-based detection (C# [ApiController], [Controller])
        if symbol.structured_docs:
            attrs = symbol.structured_docs.get('attributes', [])
            if any('Controller' in str(attr) for attr in attrs):
                return True
        
        return False
    
    @staticmethod
    def _is_service(name: str, parent_name: str, file_path: str) -> bool:
        """Detect if symbol is a service."""
        name_lower = name.lower()
        parent_lower = parent_name.lower()
        
        # Name patterns
        service_patterns = ['service', 'manager', 'handler', 'processor', 'provider']
        if any(pattern in name_lower for pattern in service_patterns):
            return True
        
        if any(pattern in parent_lower for pattern in service_patterns):
            return True
        
        # Path patterns
        if any(pattern in file_path for pattern in ['services/', 'service/', 'handlers/', 'business/']):
            return True
        
        return False
    
    @staticmethod
    def _is_repository(name: str, parent_name: str, file_path: str) -> bool:
        """Detect if symbol is a repository."""
        name_lower = name.lower()
        parent_lower = parent_name.lower()
        
        # Name patterns
        repo_patterns = ['repository', 'repo', 'store', 'dao', 'dataaccess']
        if any(pattern in name_lower for pattern in repo_patterns):
            return True
        
        if any(pattern in parent_lower for pattern in repo_patterns):
            return True
        
        # Path patterns
        if any(pattern in file_path for pattern in [
            'repositories/', 'repository/', 
            'data/', 'dataaccess/', 'dal/',
            'persistence/', 'stores/'
        ]):
            return True
        
        return False
    
    @staticmethod
    def _is_database(name: str, parent_name: str, file_path: str) -> bool:
        """Detect if symbol is database-related."""
        name_lower = name.lower()
        parent_lower = parent_name.lower()
        
        # Name patterns for database contexts and connections
        db_patterns = ['dbcontext', 'database', 'connection', 'dbset', 'context']
        if any(pattern in name_lower for pattern in db_patterns):
            return True
        
        if any(pattern in parent_lower for pattern in db_patterns):
            return True
        
        # ORM-specific patterns
        orm_patterns = ['entityframework', 'ef.', 'sequelize', 'typeorm', 'mongoose']
        if any(pattern in name_lower for pattern in orm_patterns):
            return True
        
        return False
    
    @staticmethod
    def _is_middleware(name: str, parent_name: str, file_path: str) -> bool:
        """Detect if symbol is middleware."""
        name_lower = name.lower()
        parent_lower = parent_name.lower()
        
        # Name patterns
        if 'middleware' in name_lower or 'middleware' in parent_lower:
            return True
        
        # Path patterns
        if 'middleware' in file_path:
            return True
        
        return False
    
    @staticmethod
    def _is_validator(name: str, parent_name: str, file_path: str) -> bool:
        """Detect if symbol is a validator."""
        name_lower = name.lower()
        parent_lower = parent_name.lower()
        
        # Name patterns
        if 'validator' in name_lower or 'validation' in name_lower:
            return True
        
        if 'validator' in parent_lower or 'validation' in parent_lower:
            return True
        
        # Path patterns
        if any(pattern in file_path for pattern in ['validators/', 'validation/']):
            return True
        
        return False
    
    @staticmethod
    def _is_mapper(name: str, parent_name: str, file_path: str) -> bool:
        """Detect if symbol is a mapper."""
        name_lower = name.lower()
        parent_lower = parent_name.lower()
        
        # Name patterns
        mapper_patterns = ['mapper', 'mapping', 'profile']
        if any(pattern in name_lower for pattern in mapper_patterns):
            return True
        
        if any(pattern in parent_lower for pattern in mapper_patterns):
            return True
        
        # Path patterns
        if any(pattern in file_path for pattern in ['mappers/', 'mapping/', 'mappings/']):
            return True
        
        return False
    
    @staticmethod
    def _is_model(name: str, parent_name: str, file_path: str, symbol: Symbol) -> bool:
        """Detect if symbol is a model/entity."""
        # Path patterns
        if any(pattern in file_path for pattern in [
            'models/', 'model/', 
            'entities/', 'entity/',
            'domain/', 'dtos/', 'dto/',
            'viewmodels/', 'contracts/'
        ]):
            # Only consider classes as models
            if symbol.kind == SymbolKindEnum.CLASS:
                return True
        
        # Name patterns (less reliable, use only with path)
        name_lower = name.lower()
        model_patterns = ['dto', 'viewmodel', 'entity', 'model']
        if any(name_lower.endswith(pattern) for pattern in model_patterns):
            if symbol.kind == SymbolKindEnum.CLASS:
                return True
        
        return False
    
    @staticmethod
    def _is_utility(name: str, parent_name: str, file_path: str) -> bool:
        """Detect if symbol is a utility."""
        name_lower = name.lower()
        parent_lower = parent_name.lower()
        
        # Name patterns
        util_patterns = ['helper', 'util', 'utility', 'extension', 'common']
        if any(pattern in name_lower for pattern in util_patterns):
            return True
        
        if any(pattern in parent_lower for pattern in util_patterns):
            return True
        
        # Path patterns
        if any(pattern in file_path for pattern in [
            'helpers/', 'utils/', 'utilities/',
            'extensions/', 'common/'
        ]):
            return True
        
        return False
