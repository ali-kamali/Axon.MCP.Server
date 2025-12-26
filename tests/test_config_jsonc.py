"""Test config extractor with JSONC (JSON with comments)."""
import pytest
from src.extractors.config_extractor import ConfigExtractor


def test_strip_json_comments():
    """Test that comments are properly stripped from JSON."""
    extractor = ConfigExtractor(None)
    
    # Test single-line comments
    jsonc = """
    {
        "key1": "value1", // This is a comment
        // "commented_key": "should not appear",
        "key2": "value2"
    }
    """
    cleaned = extractor._strip_json_comments(jsonc)
    assert "//" not in cleaned
    assert '"key1"' in cleaned
    assert '"commented_key"' not in cleaned
    
    # Test multi-line comments
    jsonc2 = """
    {
        "key1": "value1",
        /* This is a
           multi-line comment */
        "key2": "value2"
    }
    """
    cleaned2 = extractor._strip_json_comments(jsonc2)
    assert "/*" not in cleaned2
    assert "*/" not in cleaned2
    assert '"key1"' in cleaned2
    assert '"key2"' in cleaned2
    
    # Test trailing commas
    jsonc3 = """
    {
        "key1": "value1",
        "array": [1, 2, 3,],  // trailing comma in array
    }
    """
    cleaned3 = extractor._strip_json_comments(jsonc3)
    # Should remove trailing comma before ]
    assert '3,]' not in cleaned3
    assert '3]' in cleaned3 or cleaned3.count(',]') == 0
    
    print("✅ All comment stripping tests passed!")


def test_real_world_appsettings():
    """Test with real-world appsettings.Development.json content."""
    extractor = ConfigExtractor(None)
    
    jsonc = """{
  "Logging": {
    "LogLevel": {
      "Default": "Information", // Default log level
      "Microsoft.AspNetCore": "Warning"
    }
  },
  /* Database Configuration */
  "ConnectionStrings": {
    "DefaultConnection": "Server=localhost;Database=MyDb;", // Dev DB
  },
  "AllowedHosts": "*"  // Allow all hosts in dev
}"""
    
    cleaned = extractor._strip_json_comments(jsonc)
    
    # Should be valid JSON after cleaning
    import json
    try:
        data = json.loads(cleaned)
        assert "Logging" in data
        assert "ConnectionStrings" in data
        assert data["AllowedHosts"] == "*"
        print("✅ Real-world appsettings test passed!")
    except json.JSONDecodeError as e:
        print(f"❌ Failed to parse cleaned JSON: {e}")
        print(f"Cleaned content:\n{cleaned}")
        raise


if __name__ == "__main__":
    test_strip_json_comments()
    test_real_world_appsettings()
    print("\n✅ All JSONC tests passed!")
