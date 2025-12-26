
import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

# Adjust path to allow imports from src
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.parsers.nuget_parser import NuGetParser
from src.parsers.npm_parser import NpmParser
from src.parsers.python_dependency_parser import PythonDependencyParser
from src.extractors.dependency_extractor import DependencyExtractor

async def verify_parsers():
    print("Starting parser verification...")
    
    # Create temp directory
    temp_dir = Path(tempfile.mkdtemp())
    print(f"Created temp dir: {temp_dir}")
    
    try:
        # 1. Verify NuGet Parser
        print("\n--- Testing NuGet Parser ---")
        nuget_parser = NuGetParser()
        
        # Create sample .csproj
        csproj_content = """
        <Project Sdk="Microsoft.NET.Sdk">
          <ItemGroup>
            <PackageReference Include="Newtonsoft.Json" Version="13.0.1" />
            <PackageReference Include="Microsoft.EntityFrameworkCore" Version="6.0.0" />
          </ItemGroup>
        </Project>
        """
        csproj_path = temp_dir / "test.csproj"
        with open(csproj_path, "w") as f:
            f.write(csproj_content)
            
        packages = nuget_parser.parse_file(csproj_path)
        print(f"Parsed {len(packages)} NuGet packages")
        for p in packages:
            print(f"  - {p.package_name} ({p.version})")
            
        assert len(packages) == 2
        assert packages[0].package_name == "Newtonsoft.Json"
        assert packages[0].version == "13.0.1"
        print("[PASS] NuGet Parser passed")

        # 2. Verify npm Parser
        print("\n--- Testing npm Parser ---")
        npm_parser = NpmParser()
        
        # Create sample package.json
        package_json_content = """
        {
          "dependencies": {
            "react": "^17.0.2",
            "axios": "0.21.1"
          },
          "devDependencies": {
            "typescript": "^4.3.5"
          }
        }
        """
        package_json_path = temp_dir / "package.json"
        with open(package_json_path, "w") as f:
            f.write(package_json_content)
            
        packages = npm_parser.parse_file(package_json_path)
        print(f"Parsed {len(packages)} npm packages")
        for p in packages:
            print(f"  - {p.package_name} ({p.version_constraint}) [Dev: {p.is_dev_dependency}]")
            
        assert len(packages) == 3
        # Check for react
        react = next(p for p in packages if p.package_name == "react")
        assert react.version_constraint == "^17.0.2"
        assert not react.is_dev_dependency
        # Check for typescript
        ts = next(p for p in packages if p.package_name == "typescript")
        assert ts.is_dev_dependency
        print("[PASS] npm Parser passed")

        # 3. Verify Python Parser
        print("\n--- Testing Python Parser ---")
        python_parser = PythonDependencyParser()
        
        # Create sample requirements.txt
        req_content = """
        requests==2.26.0
        pandas>=1.3.0
        pytest
        """
        req_path = temp_dir / "requirements.txt"
        with open(req_path, "w") as f:
            f.write(req_content)
            
        packages = python_parser.parse_file(req_path)
        print(f"Parsed {len(packages)} Python packages")
        for p in packages:
            print(f"  - {p.package_name} ({p.version_constraint})")
            
        assert len(packages) == 3
        requests = next(p for p in packages if p.package_name == "requests")
        assert requests.version_constraint == "==2.26.0"
        assert requests.version == "2.26.0"
        print("[PASS] Python Parser passed")
        
        # 4. Verify Extractor Orchestration
        print("\n--- Testing Dependency Extractor ---")
        mock_session = MagicMock()
        # Mock execute to return a result with scalars().all() returning empty list (for file records)
        # But wait, extract_dependencies does not query file records, it walks the path.
        # It calls _clear_existing_dependencies which calls session.execute
        
        async def mock_execute(*args, **kwargs):
            return MagicMock()
            
        mock_session.execute = mock_execute
        mock_session.commit = MagicMock() # Async mock needed? No, pure mock is fine if not awaited or if awaited returns mock
        
        # We need to handle async calls on the mock if they are awaited
        # In extract_dependencies:
        # await self._clear_existing_dependencies(repository_id) -> awaits session.execute
        # await self.session.commit()
        
        # Let's just mock the methods we need
        extractor = DependencyExtractor(mock_session)
        # We need to monkeypatch the session methods to be async-like if we run this in asyncio
        # But for simplicity, we can just rely on the fact that we are running the parsers logic mostly.
        # The database part is what we want to skip.
        
        # Actually, let's just test _detect_dependency_files which is synchronous and critical
        files = extractor._detect_dependency_files(temp_dir)
        print(f"Detected {len(files)} dependency files")
        file_names = [f.name for f in files]
        print(f"Files: {file_names}")
        
        assert "test.csproj" in file_names
        assert "package.json" in file_names
        assert "requirements.txt" in file_names
        print("[PASS] Extractor file detection passed")

    except Exception as e:
        print(f"[FAIL] Verification failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        shutil.rmtree(temp_dir)
        print(f"\nCleaned up temp dir: {temp_dir}")

if __name__ == "__main__":
    asyncio.run(verify_parsers())
