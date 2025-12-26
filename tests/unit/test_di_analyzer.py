import pytest
from src.extractors.di_analyzer import DIAnalyzer
from src.parsers.csharp_parser import CSharpParser # Need parser to get AST? Or just tree_sitter directly
import tree_sitter_c_sharp as tscsharp
from tree_sitter import Language, Parser

@pytest.fixture
def parser():
    language = Language(tscsharp.language())
    parser = Parser(language)
    return parser

@pytest.fixture
def analyzer():
    return DIAnalyzer()

def test_generic_registration(parser, analyzer):
    code = """
    public void ConfigureServices(IServiceCollection services)
    {
        services.AddScoped<IMyService, MyService>();
    }
    """
    tree = parser.parse(bytes(code, "utf8"))
    registrations = analyzer.analyze(tree.root_node, code)
    
    assert len(registrations) == 1
    reg = registrations[0]
    assert reg.service_type == "IMyService"
    assert reg.implementation_type == "MyService"
    assert reg.lifetime == "Scoped"

def test_single_generic_registration(parser, analyzer):
    code = """
    services.AddSingleton<MySingleton>();
    """
    tree = parser.parse(bytes(code, "utf8"))
    registrations = analyzer.analyze(tree.root_node, code)
    
    assert len(registrations) == 1
    reg = registrations[0]
    assert reg.service_type == "MySingleton"
    assert reg.implementation_type == "MySingleton"
    assert reg.lifetime == "Singleton"

def test_typeof_registration(parser, analyzer):
    code = """
    services.AddTransient(typeof(IService), typeof(Service));
    """
    tree = parser.parse(bytes(code, "utf8"))
    registrations = analyzer.analyze(tree.root_node, code)
    
    assert len(registrations) == 1
    reg = registrations[0]
    assert reg.service_type == "IService"
    assert reg.implementation_type == "Service"
    assert reg.lifetime == "Transient"

def test_chained_registration(parser, analyzer):
    # Tests if traversal works inside blocks
    code = """
    public void Configure(IServiceCollection services) {
        if (true) {
            services.AddScoped<IFoo, Foo>();
        }
    }
    """
    tree = parser.parse(bytes(code, "utf8"))
    registrations = analyzer.analyze(tree.root_node, code)
    
    assert len(registrations) == 1
    assert registrations[0].service_type == "IFoo"

def test_ignore_non_di_methods(parser, analyzer):
    code = """
    services.AddSomethingElse<Foo>();
    """
    tree = parser.parse(bytes(code, "utf8"))
    registrations = analyzer.analyze(tree.root_node, code)
    
    assert len(registrations) == 0
