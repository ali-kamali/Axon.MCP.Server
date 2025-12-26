"""
Test ProjectResolver with sample data
"""
import sys
sys.path.insert(0, '.')

from pathlib import Path

def test_project_resolver_logic():
    """Test the path matching logic."""
    print("Testing ProjectResolver Logic")
    print("=" * 70)
    
    # Simulate projects
    projects = [
        {'id': 1, 'file_path': 'src/ProjectA/ProjectA.csproj'},
        {'id': 2, 'file_path': 'src/ProjectB/ProjectB.csproj'},
        {'id': 3, 'file_path': 'tests/ProjectA.Tests/ProjectA.Tests.csproj'},
    ]
    
    # Test files
    test_cases = [
        ('src/ProjectA/ClassA.cs', 1, 'ProjectA'),
        ('src/ProjectA/Services/UserService.cs', 1, 'ProjectA'),
        ('src/ProjectB/ClassB.cs', 2, 'ProjectB'),
        ('tests/ProjectA.Tests/ClassATests.cs', 3, 'ProjectA.Tests'),
        ('README.md', None, 'No project'),
    ]
    
    print("\nTest Cases:")
    print("-" * 70)
    
    for file_path, expected_id, description in test_cases:
        file_path_obj = Path(file_path)
        matched_id = None
        matches = []
        
        for project in projects:
            project_path = Path(project['file_path'])
            project_dir = project_path.parent
            
            try:
                file_parts = file_path_obj.parts
                project_parts = project_dir.parts
                
                if len(file_parts) >= len(project_parts):
                    if file_parts[:len(project_parts)] == project_parts:
                        matches.append((project['id'], len(project_parts)))
            except (ValueError, IndexError):
                continue
        
        if matches:
            matches.sort(key=lambda x: x[1], reverse=True)
            matched_id = matches[0][0]
        
        status = "[PASS]" if matched_id == expected_id else "[FAIL]"
        print(f"{status} | {file_path}")
        print(f"       Expected: {description} (ID: {expected_id})")
        print(f"       Got: Project ID {matched_id}")
        print()
    
    print("=" * 70)
    print("Test completed!")

if __name__ == "__main__":
    test_project_resolver_logic()
