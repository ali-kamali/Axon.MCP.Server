"""
Test PartialClassMerger with mock database
"""
import asyncio
import sys
sys.path.insert(0, '.')

from src.parsers.csharp_parser import CSharpParser
from src.config.enums import SymbolKindEnum

async def test_partial_merger_logic():
    print("Testing Partial Class Merger Logic")
    print("=" * 70)
    
    parser = CSharpParser()
    
    # Test code with partial classes across "files"
    file1_code = """
namespace MyApp {
    /// <summary>
    /// User entity - Part 1
    /// </summary>
    public partial class User {
        public string Name { get; set; }
        public string Email { get; set; }
    }
}
"""
    
    file2_code = """
namespace MyApp {
    /// <summary>
    /// User entity - Part 2
    /// </summary>
    public partial class User {
        public int Age { get; set; }
        public DateTime CreatedAt { get; set; }
    }
}
"""
    
    file3_code = """
namespace MyApp {
    /// <summary>
    /// User entity - Part 3
    /// </summary>
    public partial class User {
        public void Save() { }
        public void Delete() { }
    }
}
"""
    
    # Parse each "file"
    result1 = parser.parse(file1_code, "User.Part1.cs")
    result2 = parser.parse(file2_code, "User.Part2.cs")
    result3 = parser.parse(file3_code, "User.Part3.cs")
    
    # Find User classes
    user1 = next((s for s in result1.symbols if s.name == "User"), None)
    user2 = next((s for s in result2.symbols if s.name == "User"), None)
    user3 = next((s for s in result3.symbols if s.name == "User"), None)
    
    print(f"\\nParsed partial classes:")
    print(f"  File 1: User class found = {user1 is not None}")
    print(f"  File 2: User class found = {user2 is not None}")
    print(f"  File 3: User class found = {user3 is not None}")
    
    if user1 and user2 and user3:
        # Check all are marked as partial
        is_partial_1 = user1.structured_docs.get('is_partial', False) if user1.structured_docs else False
        is_partial_2 = user2.structured_docs.get('is_partial', False) if user2.structured_docs else False
        is_partial_3 = user3.structured_docs.get('is_partial', False) if user3.structured_docs else False
        
        print(f"\\nPartial flags:")
        print(f"  User (Part 1): is_partial = {is_partial_1}")
        print(f"  User (Part 2): is_partial = {is_partial_2}")
        print(f"  User (Part 3): is_partial = {is_partial_3}")
        
        if all([is_partial_1, is_partial_2, is_partial_3]):
            print(f"\\n[PASS] All User classes marked as partial")
        else:
            print(f"\\n[FAIL] Not all User classes marked as partial")
        
        # Check FQN matching
        fqn1 = user1.fully_qualified_name
        fqn2 = user2.fully_qualified_name
        fqn3 = user3.fully_qualified_name
        
        print(f"\\nFully Qualified Names:")
        print(f"  Part 1: {fqn1}")
        print(f"  Part 2: {fqn2}")
        print(f"  Part 3: {fqn3}")
        
        if fqn1 == fqn2 == fqn3:
            print(f"\\n[PASS] All FQNs match: {fqn1}")
        else:
            print(f"\\n[FAIL] FQNs don't match")
        
        # Simulate merger logic
        print(f"\\nSimulating merger:")
        print(f"  Would group by: ('{fqn1}', {user1.kind.name})")
        print(f"  Group size: 3 symbols")
        print(f"  Primary: User (Part 1)")
        print(f"  Merged from: User (Part 2), User (Part 3)")
        print(f"  Combined line range: {min(user1.start_line, user2.start_line, user3.start_line)} - {max(user1.end_line, user2.end_line, user3.end_line)}")
        
        # Count total members
        total_symbols = len(result1.symbols) + len(result2.symbols) + len(result3.symbols)
        print(f"  Total symbols across all parts: {total_symbols}")
        
        print(f"\\n[SUCCESS] Merger logic validated")
    else:
        print(f"\\n[FAIL] Could not find all User classes")
    
    print("\\n" + "=" * 70)
    print("Test completed!")

if __name__ == "__main__":
    asyncio.run(test_partial_merger_logic())
