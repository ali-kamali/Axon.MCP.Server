import pytest
from src.parsers.csharp_parser import CSharpParser
from src.config.enums import SymbolKindEnum

class TestCSharpMinimalAPI:
    
    def test_minimal_api_mapget(self):
        code = """
        var app = WebApplication.Create(args);
        
        app.MapGet("/api/users", () => {
            return Results.Ok("users");
        });
        
        app.Run();
        """
        
        parser = CSharpParser()
        result = parser.parse(code, "Program.cs")
        symbols = result.symbols
        
        endpoints = [s for s in symbols if s.kind == SymbolKindEnum.ENDPOINT]
        assert len(endpoints) == 1
        
        assert endpoints[0].name == "GET /api/users"
        assert endpoints[0].structured_docs['type'] == 'minimal_api'
        assert endpoints[0].structured_docs['method'] == 'GET'
        assert endpoints[0].structured_docs['path'] == '/api/users'

    def test_minimal_api_multiple_endpoints(self):
        code = """
        var app = WebApplication.Create(args);
        
        app.MapGet("/users", () => Results.Ok("users"));
        app.MapPost("/users", (User user) => Results.Created($"/users/{user.Id}", user));
        app.MapPut("/users/{id}", (int id, User user) => Results.NoContent());
        app.MapDelete("/users/{id}", (int id) => Results.NoContent());
        
        app.Run();
        """
        
        parser = CSharpParser()
        result = parser.parse(code, "Program.cs")
        symbols = result.symbols
        
        endpoints = [s for s in symbols if s.kind == SymbolKindEnum.ENDPOINT]
        assert len(endpoints) == 4
        
        assert endpoints[0].name == "GET /users"
        assert endpoints[1].name == "POST /users"
        assert endpoints[2].name == "PUT /users/{id}"
        assert endpoints[3].name == "DELETE /users/{id}"
