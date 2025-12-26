import pytest
from src.extractors.pattern_detector import PatternDetector
from src.database.models import Symbol
from src.config.enums import SymbolKindEnum, LanguageEnum

def create_test_symbol(name: str, kind: SymbolKindEnum, fqn: str = None) -> Symbol:
    """Helper to create test symbols."""
    return Symbol(
        id=1,
        file_id=1,
        language=LanguageEnum.CSHARP,
        kind=kind,
        name=name,
        fully_qualified_name=fqn or name,
        start_line=1,
        end_line=10,
        start_column=0,
        end_column=0
    )

def test_detect_controller_role():
    """Test detecting controller role."""
    symbol = create_test_symbol("UserController", SymbolKindEnum.CLASS)
    roles = PatternDetector.detect_roles(symbol)
    assert "Controller" in roles

def test_detect_service_role():
    """Test detecting service role."""
    symbol = create_test_symbol("PaymentService", SymbolKindEnum.CLASS)
    roles = PatternDetector.detect_roles(symbol)
    assert "Service" in roles

def test_detect_repository_role():
    """Test detecting repository role."""
    symbol = create_test_symbol("UserRepository", SymbolKindEnum.CLASS)
    roles = PatternDetector.detect_roles(symbol)
    assert "Repository" in roles

def test_detect_model_role():
    """Test detecting model role."""
    symbol = create_test_symbol("UserModel", SymbolKindEnum.CLASS)
    roles = PatternDetector.detect_roles(symbol)
    assert "Model" in roles

def test_detect_utility_role():
    """Test detecting utility role."""
    symbol = create_test_symbol("StringHelper", SymbolKindEnum.CLASS)
    roles = PatternDetector.detect_roles(symbol)
    assert "Utility" in roles

def test_detect_multiple_roles():
    """Test detecting multiple roles (though unusual)."""
    # This shouldn't happen in practice, but the detector should handle it
    symbol = create_test_symbol("UserServiceController", SymbolKindEnum.CLASS)
    roles = PatternDetector.detect_roles(symbol)
    assert "Service" in roles
    assert "Controller" in roles

def test_detect_no_roles():
    """Test when no roles are detected."""
    symbol = create_test_symbol("RandomClass", SymbolKindEnum.CLASS)
    roles = PatternDetector.detect_roles(symbol)
    assert len(roles) == 0

def test_detect_role_from_fqn():
    """Test detecting role from fully qualified name."""
    symbol = create_test_symbol(
        "MyClass",
        SymbolKindEnum.CLASS,
        fqn="Api.Controllers.UserController"
    )
    roles = PatternDetector.detect_roles(symbol)
    assert "Controller" in roles

def test_detect_api_endpoint_role():
    """Test detecting API endpoint role."""
    symbol = create_test_symbol("UserApiEndpoint", SymbolKindEnum.CLASS)
    roles = PatternDetector.detect_roles(symbol)
    assert "Controller" in roles  # API is a controller keyword

def test_detect_dao_role():
    """Test detecting DAO role (data access object)."""
    symbol = create_test_symbol("UserDao", SymbolKindEnum.CLASS)
    roles = PatternDetector.detect_roles(symbol)
    assert "Repository" in roles  # DAO is a repository keyword

def test_detect_dto_role():
    """Test detecting DTO role (data transfer object)."""
    symbol = create_test_symbol("UserDto", SymbolKindEnum.CLASS)
    roles = PatternDetector.detect_roles(symbol)
    assert "Model" in roles  # DTO is a model keyword

def test_detect_manager_role():
    """Test detecting manager role."""
    symbol = create_test_symbol("ConnectionManager", SymbolKindEnum.CLASS)
    roles = PatternDetector.detect_roles(symbol)
    assert "Service" in roles  # Manager is a service keyword

def test_detect_handler_role():
    """Test detecting handler role."""
    symbol = create_test_symbol("EventHandler", SymbolKindEnum.CLASS)
    roles = PatternDetector.detect_roles(symbol)
    assert "Service" in roles  # Handler is a service keyword

def test_detect_factory_pattern():
    """Test detecting factory pattern."""
    factory_symbol = create_test_symbol("UserFactory", SymbolKindEnum.CLASS)
    builder_symbol = create_test_symbol("QueryBuilder", SymbolKindEnum.CLASS)
    normal_symbol = create_test_symbol("UserClass", SymbolKindEnum.CLASS)
    
    symbols = [factory_symbol, builder_symbol, normal_symbol]
    factories = PatternDetector.detect_factory_pattern(symbols)
    
    assert len(factories) == 2
    assert factory_symbol in factories
    assert builder_symbol in factories
    assert normal_symbol not in factories

def test_detect_factory_pattern_no_factories():
    """Test detecting factory pattern when there are none."""
    symbol1 = create_test_symbol("UserService", SymbolKindEnum.CLASS)
    symbol2 = create_test_symbol("UserRepository", SymbolKindEnum.CLASS)
    
    symbols = [symbol1, symbol2]
    factories = PatternDetector.detect_factory_pattern(symbols)
    
    assert len(factories) == 0

def test_detect_factory_pattern_case_insensitive():
    """Test that factory detection is case insensitive."""
    symbol = create_test_symbol("userFACTORY", SymbolKindEnum.CLASS)
    factories = PatternDetector.detect_factory_pattern([symbol])
    
    assert len(factories) == 1
    assert symbol in factories

def test_detect_factory_pattern_only_classes():
    """Test that factory detection only works on classes."""
    factory_method = create_test_symbol("CreateFactory", SymbolKindEnum.METHOD)
    factories = PatternDetector.detect_factory_pattern([factory_method])
    
    assert len(factories) == 0

def test_roles_case_insensitive():
    """Test that role detection is case insensitive."""
    symbol = create_test_symbol("USERCONTROLLER", SymbolKindEnum.CLASS)
    roles = PatternDetector.detect_roles(symbol)
    assert "Controller" in roles

