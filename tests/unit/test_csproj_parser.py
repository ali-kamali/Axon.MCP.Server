"""Tests for csproj parser."""

import pytest
from src.parsers.csproj_parser import CsProjParser
from src.config.enums import SymbolKindEnum


class TestCsProjParser:
    """Test csproj parser functionality."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.parser = CsProjParser()
    
    def test_parse_package_references(self):
        """Test parsing NuGet package references."""
        csproj_content = """<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="8.0.0" />
    <PackageReference Include="Swashbuckle.AspNetCore" Version="6.5.0" />
    <PackageReference Include="Serilog" Version="3.1.0" PrivateAssets="all" />
  </ItemGroup>
</Project>"""
        
        result = self.parser.parse(csproj_content, "MyProject.csproj")
        
        assert result.language.value == "csharp"
        
        # Check for package references
        packages = [s for s in result.symbols if s.kind == SymbolKindEnum.CONSTANT 
                   and 'nuget_package' in str(s.structured_docs)]
        assert len(packages) == 3
        
        # Check specific package
        ef_package = next(s for s in packages if "EntityFrameworkCore" in s.name)
        assert ef_package.structured_docs['version'] == "8.0.0"
        assert ef_package.structured_docs['is_dev_dependency'] == False
        
        # Check dev dependency
        serilog = next(s for s in packages if "Serilog" in s.name)
        assert serilog.structured_docs['is_dev_dependency'] == True
    
    def test_parse_project_references(self):
        """Test parsing project references."""
        csproj_content = """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <ProjectReference Include="../MyLibrary/MyLibrary.csproj" />
    <ProjectReference Include="../Common/Common.csproj" />
  </ItemGroup>
</Project>"""
        
        result = self.parser.parse(csproj_content, "MyApp.csproj")
        
        # Check for project references (stored as modules)
        projects = [s for s in result.symbols if s.kind == SymbolKindEnum.MODULE]
        assert len(projects) == 2
        
        # Check project names
        names = [s.name for s in projects]
        assert "MyLibrary" in names
        assert "Common" in names
        
        # Check imports (project references are also stored as imports)
        assert len(result.imports) == 2
    
    def test_parse_project_properties(self):
        """Test parsing project properties."""
        csproj_content = """<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <OutputType>Exe</OutputType>
    <AssemblyName>MyCustomApp</AssemblyName>
  </PropertyGroup>
</Project>"""
        
        result = self.parser.parse(csproj_content, "MyProject.csproj")
        
        # Check for properties
        properties = [s for s in result.symbols if s.kind == SymbolKindEnum.PROPERTY]
        assert len(properties) == 3
        
        # Verify property values
        target_fw = next(s for s in properties if s.name == "TargetFramework")
        assert target_fw.structured_docs['value'] == "net8.0"
        
        output_type = next(s for s in properties if s.name == "OutputType")
        assert output_type.structured_docs['value'] == "Exe"
        
        assembly_name = next(s for s in properties if s.name == "AssemblyName")
        assert assembly_name.structured_docs['value'] == "MyCustomApp"
    
    def test_invalid_xml(self):
        """Test handling of invalid XML."""
        invalid_xml = "<Project>This is not valid XML"
        
        result = self.parser.parse(invalid_xml, "Invalid.csproj")
        
        assert len(result.parse_errors) > 0
        assert "XML parsing error" in result.parse_errors[0]
    
    def test_empty_csproj(self):
        """Test parsing minimal csproj."""
        minimal_csproj = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
  </PropertyGroup>
</Project>"""
        
        result = self.parser.parse(minimal_csproj, "Minimal.csproj")
        
        assert len(result.parse_errors) == 0
        # Should have at least the TargetFramework property
        assert len(result.symbols) >= 1

