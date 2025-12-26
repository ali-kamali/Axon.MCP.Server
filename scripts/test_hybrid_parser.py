import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.parsers import parse_file
from src.parsers.hybrid_parser import HybridCSharpParser
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

def test_hybrid_parser():
    # Create a dummy C# file
    test_file = project_root / "test_hybrid.cs"
    code = """
    using System;
    using System.Collections.Generic;

    namespace TestNamespace
    {
        public interface ITestInterface
        {
            void InterfaceMethod();
        }

        public class TestClass : ITestInterface
        {
            public void InterfaceMethod()
            {
                Console.WriteLine("Implemented");
            }

            public void GenericMethod<T>(T item) where T : class
            {
                Console.WriteLine(item);
            }
        }
    }
    """
    
    with open(test_file, "w") as f:
        f.write(code)
    
    try:
        print(f"Testing hybrid parser on {test_file}...")
        
        # Use the factory (which should now return HybridCSharpParser)
        # This will internally call asyncio.run()
        result = parse_file(test_file)
        
        print(f"Parse successful: {len(result.symbols)} symbols found")
        
        roslyn_active = False
        for symbol in result.symbols:
            print(f"- {symbol.kind.name}: {symbol.name} ({symbol.fully_qualified_name})")
            if symbol.structured_docs and symbol.structured_docs.get('roslyn'):
                roslyn_active = True
                print(f"  Roslyn Metadata: {symbol.structured_docs['roslyn']}")
                
        if roslyn_active:
            print("\nSUCCESS: Roslyn integration is working!")
        else:
            print("\nWARNING: Roslyn integration did NOT return metadata (fallback to Tree-sitter?)")
            
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if test_file.exists():
            os.remove(test_file)

if __name__ == "__main__":
    test_hybrid_parser()
