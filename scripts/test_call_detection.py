"""Test call detection on actual repository files."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.session import AsyncSessionLocal
from src.database.models import Repository, File, Symbol
from src.extractors.call_analyzer import CSharpCallAnalyzer
from src.parsers import ParserFactory
from sqlalchemy import select
from src.config.enums import SymbolKindEnum, LanguageEnum


async def test_call_detection():
    """Test call detection on a sample method."""
    
    async with AsyncSessionLocal() as session:
        # Get first repository
        result = await session.execute(
            select(Repository).limit(1)
        )
        repo = result.scalar_one_or_none()
        
        if not repo:
            print("❌ No repositories found")
            return
        
        print(f"📦 Testing repository: {repo.name}")
        
        # Get a C# method
        result = await session.execute(
            select(Symbol, File)
            .join(File, Symbol.file_id == File.id)
            .where(
                File.repository_id == repo.id,
                Symbol.kind == SymbolKindEnum.METHOD,
                Symbol.language == LanguageEnum.CSHARP
            )
            .limit(5)
        )
        
        methods = result.all()
        
        if not methods:
            print("❌ No C# methods found")
            return
        
        print(f"\n✅ Found {len(methods)} methods to test\n")
        
        # Get repository path
        from src.gitlab.repository_manager import RepositoryManager
        from src.azuredevops.repository_manager import AzureDevOpsRepositoryManager
        from src.config.enums import SourceControlProviderEnum
        
        if repo.provider == SourceControlProviderEnum.AZUREDEVOPS:
            repo_manager = AzureDevOpsRepositoryManager()
            repo_path = repo_manager.get_repository_path(repo.azuredevops_project_name, repo.name)
        else:
            repo_manager = RepositoryManager()
            repo_path = repo_manager.cache_dir / repo.path_with_namespace.replace("/", "_")
        
        # Test each method
        for symbol, file in methods:
            print(f"🔍 Testing: {symbol.name} in {file.path}")
            print(f"   Lines: {symbol.start_line}-{symbol.end_line}")
            
            file_path = repo_path / file.path
            
            if not file_path.exists():
                print(f"   ⚠️  File not found: {file_path}")
                continue
            
            try:
                # Read file
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    code = f.read()
                
                # Parse with tree-sitter
                parser = ParserFactory.get_parser(LanguageEnum.CSHARP)
                tree = parser.parser.parse(bytes(code, "utf8"))
                
                # Find the method node
                def find_method_node(node, target_line):
                    """Find method node at target line."""
                    if node.type in ['method_declaration', 'constructor_declaration']:
                        if node.start_point[0] + 1 == target_line:
                            return node
                    
                    for child in node.children:
                        result = find_method_node(child, target_line)
                        if result:
                            return result
                    return None
                
                method_node = find_method_node(tree.root_node, symbol.start_line)
                
                if not method_node:
                    print(f"   ⚠️  Method node not found at line {symbol.start_line}")
                    continue
                
                # Extract calls
                analyzer = CSharpCallAnalyzer()
                calls = analyzer.extract_calls(method_node, code)
                
                print(f"   ✅ Found {len(calls)} calls:")
                for call in calls[:5]:  # Show first 5
                    receiver_str = f"{call.receiver}." if call.receiver else ""
                    async_str = "await " if call.is_async else ""
                    print(f"      - {async_str}{receiver_str}{call.method_name}() at line {call.line_number}")
                
                if len(calls) > 5:
                    print(f"      ... and {len(calls) - 5} more")
                
                print()
                
            except Exception as e:
                print(f"   ❌ Error: {e}")
                import traceback
                traceback.print_exc()
                continue


if __name__ == "__main__":
    print("=" * 60)
    print("Call Detection Test")
    print("=" * 60)
    asyncio.run(test_call_detection())
