"""
Test that the CSharp parser doesn't extract local variables and parameters as references.

This test verifies the fix for the issue where ALL identifiers in method bodies
were being extracted as references, causing massive resolution failures.
"""
import sys
sys.path.insert(0, '.')

from src.parsers.csharp_parser import CSharpParser


def test_parameter_not_extracted_as_reference():
    """Test that method parameters are NOT extracted as references."""
    parser = CSharpParser()
    
    code = """
using System;

public class BusRegistrationExtension {
    public static void AddBus(IServiceCollection services, IConfiguration configuration, Assembly assembly) {
        // These are parameters - should NOT be extracted as references:
        // - services
        // - configuration
        // - assembly
        var axon = configuration.GetSection("Axon");
        var settings = axon.Get<BusSettings>();
        
        // This IS a type instantiation - SHOULD be extracted:
        var bus = new MassTransitBus();
    }
}
"""
    
    result = parser.parse(code, "test.cs")
    
    # Find the AddBus method
    add_bus_method = None
    for symbol in result.symbols:
        if symbol.name == "AddBus":
            add_bus_method = symbol
            break
    
    assert add_bus_method is not None, "AddBus method should be found"
    
    # Check references
    references = add_bus_method.references or []
    ref_names = [ref['name'] for ref in references]
    
    print(f"\nExtracted references from AddBus method:")
    for ref in references:
        print(f"  - {ref['name']} (type: {ref['type']})")
    
    # Parameters should NOT be in references
    assert 'services' not in ref_names, "Parameter 'services' should NOT be extracted as reference"
    assert 'configuration' not in ref_names, "Parameter 'configuration' should NOT be extracted as reference"
    assert 'assembly' not in ref_names, "Parameter 'assembly' should NOT be extracted as reference"
    assert 'axon' not in ref_names, "Local variable 'axon' should NOT be extracted as reference"
    assert 'settings' not in ref_names, "Local variable 'settings' should NOT be extracted as reference"
    
    # Type instantiations SHOULD be in references
    assert 'MassTransitBus' in ref_names, "Type instantiation 'MassTransitBus' SHOULD be extracted as reference"
    
    print("\n[PASS] Test passed: Parameters and local variables are NOT extracted as references")
    print("[PASS] Type instantiations ARE correctly extracted")


def test_type_references_still_extracted():
    """Test that type references (object creation, generics) are still extracted."""
    parser = CSharpParser()
    
    code = """
using System;
using System.Collections.Generic;

public class UserService {
    public void ProcessUser(string userId) {
        // These SHOULD be extracted:
        var user = new User();           // User instantiation
        var list = new List<string>();   // List and string type references
        var dict = new Dictionary<int, User>();  // Generic types
    }
}
"""
    
    result = parser.parse(code, "test.cs")
    
    # Find the ProcessUser method
    method = None
    for symbol in result.symbols:
        if symbol.name == "ProcessUser":
            method = symbol
            break
    
    assert method is not None, "ProcessUser method should be found"
    
    references = method.references or []
    ref_names = [ref['name'] for ref in references]
    
    print(f"\nExtracted references from ProcessUser method:")
    for ref in references:
        print(f"  - {ref['name']} (type: {ref['type']})")
    
    # Type instantiations should be extracted
    assert 'User' in ref_names, "User instantiation should be extracted"
    assert 'List' in ref_names, "List type should be extracted"
    assert 'Dictionary' in ref_names, "Dictionary type should be extracted"
    
    # Parameters should NOT be extracted
    assert 'userId' not in ref_names, "Parameter 'userId' should NOT be extracted"
    
    # Local variables should NOT be extracted
    assert 'user' not in ref_names, "Local variable 'user' should NOT be extracted"
    assert 'list' not in ref_names, "Local variable 'list' should NOT be extracted"
    assert 'dict' not in ref_names, "Local variable 'dict' should NOT be extracted"
    
    print("\n[PASS] Test passed: Type references are correctly extracted")
    print("[PASS] Parameters and local variables are NOT extracted")


if __name__ == "__main__":
    print("=" * 70)
    print("Testing CSharp Reference Extraction Fix")
    print("=" * 70)
    
    test_parameter_not_extracted_as_reference()
    print()
    test_type_references_still_extracted()
    
    print()
    print("=" * 70)
    print("All tests passed! [SUCCESS]")
    print("=" * 70)
