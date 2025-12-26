
import asyncio
import os
from pathlib import Path
from src.parsers.roslyn_integration import RoslynAnalyzer

async def verify_roslyn():
    analyzer = RoslynAnalyzer()
    
    if not analyzer.is_available():
        print("Roslyn analyzer not found! Test cannot run without built binaries.")
        print("Please run: docker build -f docker/Dockerfile.base -t axon-base:latest .")
        return

    print(f"Analyzer found at: {analyzer.analyzer_path}")
    print(f"Using .NET: {analyzer.use_dotnet}")

    # Note: We can't fully end-to-end test project loading here because 
    # the RoslynAnalyzer.exe/dll on the host (if present) might not have 
    # the updated MSBuild logic yet if it hasn't been built locally.
    # The user instruction is to rebuild Docker.
    
    # However, we can test basic connectivity if the binary exists.
    
    print("\nStarting basic connectivity test...")
    try:
        # Start the process
        await analyzer._ensure_process()
        print("Process started successfully.")
        
        # Test 1: Ping via analyze
        code = "public class Test { }"
        result = await analyzer.analyze_file(code, "Test.cs", use_cache=False)
        print(f"Analysis result: Success={result.success}")
        if result.success:
            print(f"Symbols found: {len(result.symbols)}")
            
        if not result.success:
            print(f"Error: {result.error}")

    except Exception as e:
        print(f"Test failed with exception: {e}")
    finally:
        if analyzer._process:
            analyzer._process.kill()

if __name__ == "__main__":
    asyncio.run(verify_roslyn())
