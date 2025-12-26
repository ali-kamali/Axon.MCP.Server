"""
Test hybrid parser - Tree-sitter + Roslyn merger
"""
import asyncio
import sys
sys.path.insert(0, '.')

from src.parsers.hybrid_parser import HybridCSharpParser

async def test_hybrid_parser():
    print("Testing Hybrid C# Parser...")
    print("=" * 60)
    
    # Initialize hybrid parser
    parser = HybridCSharpParser()
    
    # Check configuration
    info = parser.get_parser_info()
    print(f"Parser Mode: {info['mode']}")
    print(f"Tree-sitter: {'Available' if info['tree_sitter_available'] else 'Not Available'}")
    print(f"Roslyn: {'Available' if info['roslyn_available'] else 'Not Available'}")
    if info['roslyn_path']:
        print(f"Roslyn Path: {info['roslyn_path']}")
    print()
    
    # Test code with various C# features
    code = """
using System;
using System.Collections.Generic;

namespace TestNamespace {
    /// <summary>
    /// Base user class
    /// </summary>
    public class User {
        public string Name { get; set; }
        public int Age { get; set; }
        
        public virtual void Display() {
            Console.WriteLine($"User: {Name}");
        }
    }
    
    /// <summary>
    /// Admin user with elevated privileges
    /// </summary>
    public class AdminUser : User {
        public List<string> Permissions { get; set; }
        
        public override void Display() {
            Console.WriteLine($"Admin: {Name}");
        }
    }
    
    public interface IService {
        void Process();
    }
    
    public class UserService : IService {
        private User _user;
        
        public void Process() {
            _user = new User();
            _user.Display();
        }
        
        public void Dispose() {
            _user = null;
        }
    }
}
"""
    
    # Parse with hybrid parser
    print("Parsing code...")
    result = await parser.parse_async(code, "test.cs")
    
    print(f"[OK] Parsed {len(result.symbols)} symbols")
    print()
    
    # Display results
    print("Symbols Found:")
    print("-" * 60)
    
    for symbol in result.symbols:
        print(f"\n{symbol.name} ({symbol.kind.name})")
        print(f"  FQN: {symbol.fully_qualified_name or 'N/A'}")
        print(f"  Lines: {symbol.start_line}-{symbol.end_line}")
        
        if symbol.return_type:
            print(f"  Return Type: {symbol.return_type}")
        
        # Show Roslyn enrichment
        if symbol.structured_docs and 'roslyn' in symbol.structured_docs:
            roslyn_data = symbol.structured_docs['roslyn']
            print(f"  [Roslyn Data]")
            
            if roslyn_data.get('is_static'):
                print(f"    Static: Yes")
            if roslyn_data.get('is_abstract'):
                print(f"    Abstract: Yes")
            if roslyn_data.get('is_virtual'):
                print(f"    Virtual: Yes")
            if roslyn_data.get('is_override'):
                print(f"    Override: Yes")
            
            if roslyn_data.get('base_type'):
                print(f"    Base Type: {roslyn_data['base_type']}")
            
            if roslyn_data.get('interfaces'):
                print(f"    Interfaces: {', '.join(roslyn_data['interfaces'])}")
        
        # Show references
        if symbol.references:
            print(f"  References: {len(symbol.references)}")
    
    print()
    print("=" * 60)
    print("Test completed!")
    
    # Verify specific features
    print("\nVerification:")
    print("-" * 60)
    
    # Find AdminUser class
    admin_user = next((s for s in result.symbols if s.name == "AdminUser"), None)
    if admin_user:
        roslyn_data = (admin_user.structured_docs or {}).get('roslyn', {})
        base_type = roslyn_data.get('base_type')
        
        if base_type and 'User' in base_type:
            print("[OK] AdminUser inherits from User")
        else:
            print("[FAIL] AdminUser inheritance not detected")
    else:
        print("[FAIL] AdminUser class not found")
    
    # Find Display method in AdminUser
    display_override = next((s for s in result.symbols 
                            if s.name == "Display" and s.parent_name == "AdminUser"), None)
    if display_override:
        roslyn_data = (display_override.structured_docs or {}).get('roslyn', {})
        if roslyn_data.get('is_override'):
            print("[OK] Display method marked as override")
        else:
            print("[FAIL] Override not detected")
    else:
        print("[FAIL] Display override method not found")
    
    # Find UserService class
    user_service = next((s for s in result.symbols if s.name == "UserService"), None)
    if user_service:
        roslyn_data = (user_service.structured_docs or {}).get('roslyn', {})
        interfaces = roslyn_data.get('interfaces', [])
        
        if any('IService' in iface for iface in interfaces):
            print("[OK] UserService implements IService")
        else:
            print("[FAIL] Interface implementation not detected")
    else:
        print("[FAIL] UserService class not found")
    
    print()

if __name__ == "__main__":
    asyncio.run(test_hybrid_parser())
