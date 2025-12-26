"""
Unit tests for LayerDetector utility.

Tests the heuristics-based detection of architectural layers.
"""
import pytest
from src.utils.layer_detector import LayerDetector
from src.database.models import Symbol, File
from src.config.enums import SymbolKindEnum


class FakeSymbol:
    """Mock symbol for testing."""
    def __init__(self, name, parent_name=None, kind=SymbolKindEnum.METHOD, structured_docs=None):
        self.name = name
        self.parent_name = parent_name
        self.kind = kind
        self.structured_docs = structured_docs or {}


class FakeFile:
    """Mock file for testing."""
    def __init__(self, path):
        self.path = path


class TestLayerDetector:
    """Test LayerDetector layer identification."""
    
    def test_detect_controller_by_name(self):
        """Test controller detection by class name."""
        symbol = FakeSymbol("UserController", kind=SymbolKindEnum.CLASS)
        file = FakeFile("src/api/UserController.cs")
        
        layer = LayerDetector.detect_layer(symbol, file)
        assert layer == LayerDetector.CONTROLLER
    
    def test_detect_controller_by_path(self):
        """Test controller detection by file path."""
        symbol = FakeSymbol("User", kind=SymbolKindEnum.CLASS)
        file = FakeFile("Controllers/UserController.cs")
        
        layer = LayerDetector.detect_layer(symbol, file)
        assert layer == LayerDetector.CONTROLLER
    
    def test_detect_controller_by_parent(self):
        """Test controller detection by parent class name."""
        symbol = FakeSymbol("GetUser", parent_name="UserController")
        file = FakeFile("src/api/User.cs")
        
        layer = LayerDetector.detect_layer(symbol, file)
        assert layer == LayerDetector.CONTROLLER
    
    def test_detect_service_by_name(self):
        """Test service detection by name suffix."""
        symbol = FakeSymbol("UserService", kind=SymbolKindEnum.CLASS)
        file = FakeFile("src/services/UserService.cs")
        
        layer = LayerDetector.detect_layer(symbol, file)
        assert layer == LayerDetector.SERVICE
    
    def test_detect_service_by_manager_suffix(self):
        """Test service detection by Manager suffix."""
        symbol = FakeSymbol("UserManager", kind=SymbolKindEnum.CLASS)
        file = FakeFile("src/business/UserManager.cs")
        
        layer = LayerDetector.detect_layer(symbol, file)
        assert layer == LayerDetector.SERVICE
    
    def test_detect_service_by_path(self):
        """Test service detection by file path."""
        symbol = FakeSymbol("User", kind=SymbolKindEnum.CLASS)
        file = FakeFile("services/User.cs")
        
        layer = LayerDetector.detect_layer(symbol, file)
        assert layer == LayerDetector.SERVICE
    
    def test_detect_repository_by_name(self):
        """Test repository detection by name suffix."""
        symbol = FakeSymbol("UserRepository", kind=SymbolKindEnum.CLASS)
        file = FakeFile("src/data/UserRepository.cs")
        
        layer = LayerDetector.detect_layer(symbol, file)
        assert layer == LayerDetector.REPOSITORY
    
    def test_detect_repository_by_path(self):
        """Test repository detection by file path."""
        symbol = FakeSymbol("User", kind=SymbolKindEnum.CLASS)
        file = FakeFile("repositories/UserRepo.cs")
        
        layer = LayerDetector.detect_layer(symbol, file)
        assert layer == LayerDetector.REPOSITORY
    
    def test_detect_database_by_dbcontext(self):
        """Test database detection by DbContext suffix."""
        symbol = FakeSymbol("ApplicationDbContext", kind=SymbolKindEnum.CLASS)
        file = FakeFile("src/data/ApplicationDbContext.cs")
        
        layer = LayerDetector.detect_layer(symbol, file)
        assert layer == LayerDetector.DATABASE
    
    def test_detect_database_by_context_suffix(self):
        """Test database detection by Context suffix."""
        symbol = FakeSymbol("AppContext", kind=SymbolKindEnum.CLASS)
        file = FakeFile("src/data/AppContext.cs")
        
        layer = LayerDetector.detect_layer(symbol, file)
        assert layer == LayerDetector.DATABASE
    
    def test_detect_middleware_by_name(self):
        """Test middleware detection by name."""
        symbol = FakeSymbol("AuthMiddleware", kind=SymbolKindEnum.CLASS)
        file = FakeFile("src/middleware/AuthMiddleware.cs")
        
        layer = LayerDetector.detect_layer(symbol, file)
        assert layer == LayerDetector.MIDDLEWARE
    
    def test_detect_validator_by_name(self):
        """Test validator detection by name suffix."""
        symbol = FakeSymbol("UserValidator", kind=SymbolKindEnum.CLASS)
        file = FakeFile("src/validators/UserValidator.cs")
        
        layer = LayerDetector.detect_layer(symbol, file)
        assert layer == LayerDetector.VALIDATOR
    
    def test_detect_mapper_by_name(self):
        """Test mapper detection by name suffix."""
        symbol = FakeSymbol("UserMapper", kind=SymbolKindEnum.CLASS)
        file = FakeFile("src/mappers/UserMapper.cs")
        
        layer = LayerDetector.detect_layer(symbol, file)
        assert layer == LayerDetector.MAPPER
    
    def test_detect_model_by_path(self):
        """Test model detection by file path and class kind."""
        symbol = FakeSymbol("User", kind=SymbolKindEnum.CLASS)
        file = FakeFile("models/User.cs")
        
        layer = LayerDetector.detect_layer(symbol, file)
        assert layer == LayerDetector.MODEL
    
    def test_detect_model_by_entities_path(self):
        """Test model detection by entities path."""
        symbol = FakeSymbol("Product", kind=SymbolKindEnum.CLASS)
        file = FakeFile("entities/Product.cs")
        
        layer = LayerDetector.detect_layer(symbol, file)
        assert layer == LayerDetector.MODEL
    
    def test_model_not_detected_for_method(self):
        """Test that methods in models folder are not classified as models."""
        symbol = FakeSymbol("GetUser", kind=SymbolKindEnum.METHOD)
        file = FakeFile("models/User.cs")
        
        layer = LayerDetector.detect_layer(symbol, file)
        assert layer != LayerDetector.MODEL
    
    def test_detect_utility_by_helper_name(self):
        """Test utility detection by Helper suffix."""
        symbol = FakeSymbol("StringHelper", kind=SymbolKindEnum.CLASS)
        file = FakeFile("src/utils/StringHelper.cs")
        
        layer = LayerDetector.detect_layer(symbol, file)
        assert layer == LayerDetector.UTILITY
    
    def test_detect_utility_by_path(self):
        """Test utility detection by utils path."""
        symbol = FakeSymbol("Common", kind=SymbolKindEnum.CLASS)
        file = FakeFile("utils/Common.cs")
        
        layer = LayerDetector.detect_layer(symbol, file)
        assert layer == LayerDetector.UTILITY
    
    def test_unknown_layer(self):
        """Test that unrecognized symbols are marked as Unknown."""
        symbol = FakeSymbol("SomeClass", kind=SymbolKindEnum.CLASS)
        file = FakeFile("src/random/SomeClass.cs")
        
        layer = LayerDetector.detect_layer(symbol, file)
        assert layer == LayerDetector.UNKNOWN
    
    def test_priority_controller_over_service(self):
        """Test that Controller is detected even with Service in name."""
        # A class like "ServiceController" should be Controller, not Service
        symbol = FakeSymbol("ServiceController", kind=SymbolKindEnum.CLASS)
        file = FakeFile("controllers/ServiceController.cs")
        
        layer = LayerDetector.detect_layer(symbol, file)
        assert layer == LayerDetector.CONTROLLER
    
    def test_case_insensitive_detection(self):
        """Test that detection is case-insensitive."""
        symbol = FakeSymbol("usercontroller", kind=SymbolKindEnum.CLASS)
        file = FakeFile("src/CONTROLLERS/usercontroller.cs")
        
        layer = LayerDetector.detect_layer(symbol, file)
        assert layer == LayerDetector.CONTROLLER
    
    def test_get_layer_emoji_controller(self):
        """Test emoji retrieval for controller layer."""
        emoji = LayerDetector.get_layer_emoji(LayerDetector.CONTROLLER)
        assert emoji == "🎯"
    
    def test_get_layer_emoji_service(self):
        """Test emoji retrieval for service layer."""
        emoji = LayerDetector.get_layer_emoji(LayerDetector.SERVICE)
        assert emoji == "⚙️"
    
    def test_get_layer_emoji_repository(self):
        """Test emoji retrieval for repository layer."""
        emoji = LayerDetector.get_layer_emoji(LayerDetector.REPOSITORY)
        assert emoji == "🗄️"
    
    def test_get_layer_emoji_unknown(self):
        """Test emoji retrieval for unknown layer."""
        emoji = LayerDetector.get_layer_emoji(LayerDetector.UNKNOWN)
        assert emoji == "❓"
    
    def test_get_layer_emoji_invalid(self):
        """Test emoji retrieval for invalid layer."""
        emoji = LayerDetector.get_layer_emoji("InvalidLayer")
        assert emoji == "❓"
    
    def test_none_symbol(self):
        """Test handling of None symbol."""
        layer = LayerDetector.detect_layer(None, None)
        assert layer == LayerDetector.UNKNOWN
    
    def test_nested_path_detection(self):
        """Test detection with deeply nested paths."""
        symbol = FakeSymbol("UsersController", kind=SymbolKindEnum.CLASS)
        file = FakeFile("src/api/v1/controllers/UsersController.cs")
        
        layer = LayerDetector.detect_layer(symbol, file)
        assert layer == LayerDetector.CONTROLLER
    
    def test_javascript_service_detection(self):
        """Test service detection for JavaScript files."""
        symbol = FakeSymbol("userService", kind=SymbolKindEnum.CLASS)
        file = FakeFile("src/services/userService.js")
        
        layer = LayerDetector.detect_layer(symbol, file)
        assert layer == LayerDetector.SERVICE
    
    def test_typescript_controller_detection(self):
        """Test controller detection for TypeScript files."""
        symbol = FakeSymbol("UserController", kind=SymbolKindEnum.CLASS)
        file = FakeFile("src/controllers/user.controller.ts")
        
        layer = LayerDetector.detect_layer(symbol, file)
        assert layer == LayerDetector.CONTROLLER
