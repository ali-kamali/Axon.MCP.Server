"""
Simple test to verify reference extraction works without database.
"""
from src.parsers.csharp_parser import CSharpParser

code = """
using System;

namespace TestNamespace {
    public class User {
        public string Name { get; set; }
    }
    
    public class Service {
        private User _user;
        
        public void Process() {
            _user = new User();
            Console.WriteLine(_user.Name);
            
            var localName = _user.Name;
        }
    }
}
"""

parser = CSharpParser()
result = parser.parse(code, "test.cs")

print(f"Parsed {len(result.symbols)} symbols\n")

for symbol in result.symbols:
    print(f"Symbol: {symbol.name} ({symbol.kind})")
    if symbol.references:
        print(f"  References ({len(symbol.references)}):")
        for ref in symbol.references:
            print(f"    - {ref['name']} ({ref['type']}) at line {ref['line']}, col {ref['column']}")
    else:
        print(f"  No references")
    print()
