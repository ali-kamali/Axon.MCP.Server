"""
Test script for Roslyn integration.
"""
import asyncio
import sys
sys.path.insert(0, '.')

from src.parsers.roslyn_integration import RoslynAnalyzer

async def test_roslyn_integration():
    print("Testing Roslyn Integration...")
    print("=" * 60)
    
    # Initialize analyzer
    analyzer = RoslynAnalyzer()
    
    # Check availability
    if not analyzer.is_available():
        print("[FAIL] Roslyn analyzer not available")
        print(f"   Expected path: {analyzer.analyzer_path}")
        return
    
    print(f"[OK] Roslyn analyzer found at: {analyzer.analyzer_path}")
    print()
    
    # Test code
    code = """
using System;

namespace TestNamespace {
    public class User {
        public string Name { get; set; }
        public int Age { get; set; }
    }
    
    public class Service : IDisposable {
        private User _user;
        
        public void Process() {
            _user = new User();
            Console.WriteLine(_user.Name);
        }
        
        public void Dispose() {
            // cleanup
        }
    }
}
"""
    
    # Test 1: Analyze file
    print("Test 1: Analyze File")
    print("-" * 60)
    result = await analyzer.analyze_file(code, "test.cs")
    
    if result.success:
        print(f"[OK] Analysis successful!")
        print(f"   Found {len(result.symbols)} symbols:")
        for sym in result.symbols:
            print(f"   - {sym.name} ({sym.kind})")
            if sym.base_type:
                print(f"     Base: {sym.base_type}")
            if sym.interfaces:
                print(f"     Interfaces: {', '.join(sym.interfaces)}")
    else:
        print(f"[FAIL] Analysis failed: {result.error}")
    
    print()
    
    # Test 2: Get inheritance chain
    print("Test 2: Get Inheritance Chain")
    print("-" * 60)
    inheritance = await analyzer.get_inheritance_chain(code, "test.cs", "Service")
    
    if inheritance:
        print(f"[OK] Inheritance chain for 'Service':")
        print(f"   Base classes: {inheritance['base_classes']}")
        print(f"   Interfaces: {inheritance['interfaces']}")
    else:
        print("[FAIL] Could not get inheritance chain")
    
    print()
    
    # Test 3: Cache stats
    print("Test 3: Cache Statistics")
    print("-" * 60)
    stats = analyzer.get_cache_stats()
    print(f"[OK] Cache stats: {stats}")
    
    print()
    print("=" * 60)
    print("All tests completed!")

if __name__ == "__main__":
    asyncio.run(test_roslyn_integration())
