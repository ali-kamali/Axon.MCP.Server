"""
Test partial class detection in CSharpParser
"""
import sys
sys.path.insert(0, '.')

from src.parsers.csharp_parser import CSharpParser

def test_partial_detection():
    print("Testing Partial Class Detection")
    print("=" * 60)
    
    parser = CSharpParser()
    
    # Test code with partial classes
    code = """
using System;

namespace Test {
    public partial class User {
        public string Name { get; set; }
    }
    
    public partial class User {
        public int Age { get; set; }
    }
    
    public class NonPartial {
        public string Value { get; set; }
    }
    
    public partial interface IService {
        void Method1();
    }
    
    public partial interface IService {
        void Method2();
    }
}
"""
    
    result = parser.parse(code, "test.cs")
    
    print(f"Parsed {len(result.symbols)} symbols\\n")
    
    # Check partial classes
    user_classes = [s for s in result.symbols if s.name == "User"]
    print(f"Found {len(user_classes)} User class definitions")
    
    for i, user_class in enumerate(user_classes, 1):
        is_partial = user_class.structured_docs.get('is_partial', False) if user_class.structured_docs else False
        print(f"  User #{i}: is_partial = {is_partial}")
        if is_partial:
            print(f"    [PASS] Partial detected")
        else:
            print(f"    [FAIL] Partial NOT detected")
    
    # Check non-partial class
    non_partial = next((s for s in result.symbols if s.name == "NonPartial"), None)
    if non_partial:
        is_partial = non_partial.structured_docs.get('is_partial', False) if non_partial.structured_docs else False
        if not is_partial:
            print(f"\\n[PASS] NonPartial correctly identified as non-partial")
        else:
            print(f"\\n[FAIL] NonPartial incorrectly marked as partial")
    
    # Check partial interfaces
    iservice_interfaces = [s for s in result.symbols if s.name == "IService"]
    print(f"\\nFound {len(iservice_interfaces)} IService interface definitions")
    
    for i, iservice in enumerate(iservice_interfaces, 1):
        is_partial = iservice.structured_docs.get('is_partial', False) if iservice.structured_docs else False
        print(f"  IService #{i}: is_partial = {is_partial}")
        if is_partial:
            print(f"    [PASS] Partial detected")
        else:
            print(f"    [FAIL] Partial NOT detected")
    
    print("\\n" + "=" * 60)
    print("Test completed!")

if __name__ == "__main__":
    test_partial_detection()
