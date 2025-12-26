"""Tests for appsettings parser."""

import pytest
from src.parsers.appsettings_parser import AppSettingsParser
from src.config.enums import SymbolKindEnum


class TestAppSettingsParser:
    """Test appsettings parser functionality."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.parser = AppSettingsParser()
    
    def test_parse_flat_config(self):
        """Test parsing flat configuration."""
        json_content = """{
  "ApplicationName": "MyApp",
  "Version": "1.0.0",
  "Debug": true,
  "MaxConnections": 100
}"""
        result = self.parser.parse(json_content, "appsettings.json")
        
        assert result.language.value == "csharp"
        assert len(result.symbols) == 4
        
        # Check for constants (config values)
        configs = [s for s in result.symbols if s.kind == SymbolKindEnum.CONSTANT]
        assert len(configs) == 4
        
        # Verify config entries
        app_name = next(s for s in configs if s.name == "ApplicationName")
        assert app_name.structured_docs['value'] == "MyApp"
        assert app_name.structured_docs['type'] == 'configuration'
    
    def test_parse_nested_config(self):
        """Test parsing nested configuration."""
        json_content = """{
  "Database": {
    "ConnectionString": "Server=localhost;Database=test",
    "Timeout": 30
  },
  "Logging": {
    "LogLevel": {
      "Default": "Information",
      "Microsoft": "Warning"
    }
  }
}"""
        result = self.parser.parse(json_content, "appsettings.json")
        
        configs = [s for s in result.symbols if s.kind == SymbolKindEnum.CONSTANT]
        
        # Check flattened keys
        keys = [s.name for s in configs]
        assert "Database:ConnectionString" in keys
        assert "Database:Timeout" in keys
        assert "Logging:LogLevel:Default" in keys
        assert "Logging:LogLevel:Microsoft" in keys
    
    def test_detect_environment(self):
        """Test environment detection from filename."""
        json_content = '{"Key": "Value"}'
        
        # Test different environments
        dev_result = self.parser.parse(json_content, "appsettings.Development.json")
        prod_result = self.parser.parse(json_content, "appsettings.Production.json")
        staging_result = self.parser.parse(json_content, "appsettings.Staging.json")
        
        assert dev_result.symbols[0].structured_docs['environment'] == 'development'
        assert prod_result.symbols[0].structured_docs['environment'] == 'production'
        assert staging_result.symbols[0].structured_docs['environment'] == 'staging'
    
    def test_detect_secrets(self):
        """Test secret detection in configuration."""
        json_content = """{
  "Database": {
    "ConnectionString": "Server=localhost;Password=secret123",
    "Username": "admin"
  },
  "ApiKey": "sk_test_1234567890",
  "SecretKey": "my-secret-key",
  "PublicUrl": "https://example.com"
}"""
        result = self.parser.parse(json_content, "appsettings.json")
        
        configs = [s for s in result.symbols if s.kind == SymbolKindEnum.CONSTANT]
        
        # Check secrets are detected
        conn_string = next(s for s in configs if "ConnectionString" in s.name)
        assert conn_string.structured_docs['is_secret'] == True
        
        api_key = next(s for s in configs if "ApiKey" in s.name)
        assert api_key.structured_docs['is_secret'] == True
        
        # Public URL should not be a secret
        public_url = next(s for s in configs if "PublicUrl" in s.name)
        assert public_url.structured_docs['is_secret'] == False
    
    def test_value_types(self):
        """Test that value types are correctly identified."""
        json_content = """{
  "StringValue": "hello",
  "NumberValue": 42,
  "BoolValue": true,
  "NullValue": null,
  "ArrayValue": [1, 2, 3],
  "ObjectValue": {"nested": "value"}
}"""
        result = self.parser.parse(json_content, "appsettings.json")
        
        configs = {s.name: s for s in result.symbols}
        
        assert configs["StringValue"].structured_docs['value_type'] == 'string'
        assert configs["NumberValue"].structured_docs['value_type'] == 'number'
        assert configs["BoolValue"].structured_docs['value_type'] == 'boolean'
        assert configs["NullValue"].structured_docs['value_type'] == 'null'
        # Arrays and objects are not flattened, so they won't be in the output
    
    def test_invalid_json(self):
        """Test handling of invalid JSON."""
        invalid_json = "{ this is not valid json }"
        
        result = self.parser.parse(invalid_json, "appsettings.json")
        
        assert len(result.parse_errors) > 0
        assert "JSON parsing error" in result.parse_errors[0]

