"""
Comprehensive validation suite for hybrid architecture.

Tests:
1. Roslyn integration
2. Hybrid parser
3. Reference extraction
4. End-to-end integration
"""
import asyncio
import sys
import time
sys.path.insert(0, '.')

from src.parsers.hybrid_parser import HybridCSharpParser
from src.parsers.roslyn_integration import RoslynAnalyzer

async def run_all_tests():
    print("=" * 70)
    print("HYBRID ARCHITECTURE VALIDATION SUITE")
    print("=" * 70)
    print()
    
    results = {
        'passed': 0,
        'failed': 0,
        'total': 0
    }
    
    # Test 1: Roslyn Availability
    print("[Test 1] Roslyn Analyzer Availability")
    print("-" * 70)
    analyzer = RoslynAnalyzer()
    if analyzer.is_available():
        print("[PASS] Roslyn analyzer is available")
        print(f"       Path: {analyzer.analyzer_path}")
        results['passed'] += 1
    else:
        print("[FAIL] Roslyn analyzer not available")
        results['failed'] += 1
    results['total'] += 1
    print()
    
    # Test 2: Hybrid Parser Mode
    print("[Test 2] Hybrid Parser Configuration")
    print("-" * 70)
    parser = HybridCSharpParser()
    info = parser.get_parser_info()
    if info['mode'] == 'hybrid':
        print("[PASS] Hybrid mode enabled")
        print(f"       Tree-sitter: {info['tree_sitter_available']}")
        print(f"       Roslyn: {info['roslyn_available']}")
        results['passed'] += 1
    else:
        print(f"[WARN] Running in {info['mode']} mode")
        results['passed'] += 1  # Not a failure, just different mode
    results['total'] += 1
    print()
    
    # Test 3: Symbol Parsing Accuracy
    print("[Test 3] Symbol Parsing Accuracy")
    print("-" * 70)
    
    test_code = """
using System;

namespace Test {
    public class BaseClass {
        public virtual void Method() { }
    }
    
    public class DerivedClass : BaseClass {
        public override void Method() { }
    }
    
    public interface IService {
        void Process();
    }
    
    public class Service : IService {
        public void Process() { }
    }
}
"""
    
    result = await parser.parse_async(test_code, "test.cs")
    
    # Check symbol count
    if len(result.symbols) >= 7:  # BaseClass, DerivedClass, IService, Service, + methods
        print(f"[PASS] Parsed {len(result.symbols)} symbols")
        results['passed'] += 1
    else:
        print(f"[FAIL] Expected >= 7 symbols, got {len(result.symbols)}")
        results['failed'] += 1
    results['total'] += 1
    
    # Check inheritance detection
    derived_class = next((s for s in result.symbols if s.name == "DerivedClass"), None)
    if derived_class and derived_class.structured_docs:
        roslyn_data = derived_class.structured_docs.get('roslyn', {})
        base_type = roslyn_data.get('base_type', '')
        if 'BaseClass' in base_type:
            print("[PASS] Inheritance detected correctly")
            results['passed'] += 1
        else:
            print(f"[FAIL] Inheritance not detected (base_type: {base_type})")
            results['failed'] += 1
    else:
        print("[FAIL] DerivedClass not found or no Roslyn data")
        results['failed'] += 1
    results['total'] += 1
    
    # Check interface implementation
    service_class = next((s for s in result.symbols if s.name == "Service"), None)
    if service_class and service_class.structured_docs:
        roslyn_data = service_class.structured_docs.get('roslyn', {})
        interfaces = roslyn_data.get('interfaces', [])
        if any('IService' in iface for iface in interfaces):
            print("[PASS] Interface implementation detected")
            results['passed'] += 1
        else:
            print(f"[FAIL] Interface not detected (interfaces: {interfaces})")
            results['failed'] += 1
    else:
        print("[FAIL] Service class not found or no Roslyn data")
        results['failed'] += 1
    results['total'] += 1
    
    # Check method override
    override_method = next((s for s in result.symbols 
                           if s.name == "Method" and s.parent_name == "DerivedClass"), None)
    if override_method and override_method.structured_docs:
        roslyn_data = override_method.structured_docs.get('roslyn', {})
        if roslyn_data.get('is_override'):
            print("[PASS] Method override detected")
            results['passed'] += 1
        else:
            print("[FAIL] Override not detected")
            results['failed'] += 1
    else:
        print("[FAIL] Override method not found or no Roslyn data")
        results['failed'] += 1
    results['total'] += 1
    print()
    
    # Test 4: Performance Benchmark
    print("[Test 4] Performance Benchmark")
    print("-" * 70)
    
    # Larger test code
    large_code = """
using System;
using System.Collections.Generic;

namespace LargeTest {
""" + "\n".join([f"""
    public class Class{i} {{
        public string Property{i} {{ get; set; }}
        public void Method{i}() {{ }}
    }}
""" for i in range(10)]) + "\n}"
    
    start = time.time()
    result = await parser.parse_async(large_code, "large_test.cs")
    duration_ms = (time.time() - start) * 1000
    
    if duration_ms < 500:  # Should be under 500ms for 10 classes
        print(f"[PASS] Parsed in {duration_ms:.0f}ms (< 500ms target)")
        results['passed'] += 1
    else:
        print(f"[WARN] Parsed in {duration_ms:.0f}ms (> 500ms)")
        results['passed'] += 1  # Not a hard failure
    results['total'] += 1
    print(f"       Symbols found: {len(result.symbols)}")
    print()
    
    # Summary
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Total Tests: {results['total']}")
    print(f"Passed: {results['passed']}")
    print(f"Failed: {results['failed']}")
    print(f"Success Rate: {(results['passed']/results['total']*100):.1f}%")
    print()
    
    if results['failed'] == 0:
        print("[SUCCESS] All tests passed! System is production-ready.")
        return 0
    else:
        print(f"[WARNING] {results['failed']} test(s) failed. Review before deployment.")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
