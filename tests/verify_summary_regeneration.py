import asyncio
import hashlib
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch
import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils.module_summary_generator import ModuleSummaryGenerator
from src.database.models import ModuleSummary, File

async def test_summary_regeneration():
    print("Starting verification test...")
    
    # Mock session
    session = AsyncMock()
    
    # Mock existing summary
    existing_summary = ModuleSummary(
        id=1,
        repository_id=1,
        module_path="src/test",
        content_hash="old_hash",
        version=1
    )
    
    # Setup mock return for existing summary check
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_summary
    session.execute.return_value = mock_result
    
    # Create generator
    generator = ModuleSummaryGenerator(session)
    
    # Mock internal methods to isolate logic
    generator._calculate_module_hash = AsyncMock(return_value="old_hash")
    generator.module_identifier.get_module_symbols = AsyncMock(return_value=[])
    generator._get_entry_point_contents = AsyncMock(return_value={})
    generator.llm_summarizer.summarize_module = AsyncMock(return_value={"summary": "New Summary"})
    
    # Test Case 1: Content hash matches, force_regenerate=False
    print("\nTest Case 1: Content hash matches, force_regenerate=False")
    module_info = MagicMock()
    module_info.path = "src/test"
    
    result = await generator.generate_or_update_summary(
        repository_id=1,
        module_info=module_info,
        force_regenerate=False
    )
    
    if result == existing_summary and generator.llm_summarizer.summarize_module.call_count == 0:
        print("SUCCESS: Regeneration skipped as expected.")
    else:
        print("FAILURE: Regeneration was not skipped.")
        print(f"Result: {result}")
        print(f"LLM call count: {generator.llm_summarizer.summarize_module.call_count}")

    # Test Case 2: Content hash matches, force_regenerate=True
    print("\nTest Case 2: Content hash matches, force_regenerate=True")
    generator.llm_summarizer.summarize_module.reset_mock()
    
    result = await generator.generate_or_update_summary(
        repository_id=1,
        module_info=module_info,
        force_regenerate=True
    )
    
    if generator.llm_summarizer.summarize_module.call_count == 1:
        print("SUCCESS: Regeneration forced as expected.")
    else:
        print("FAILURE: Regeneration was not forced.")
        
    # Test Case 3: Content hash differs, force_regenerate=False
    print("\nTest Case 3: Content hash differs, force_regenerate=False")
    generator.llm_summarizer.summarize_module.reset_mock()
    generator._calculate_module_hash.return_value = "new_hash"
    
    result = await generator.generate_or_update_summary(
        repository_id=1,
        module_info=module_info,
        force_regenerate=False
    )
    
    if generator.llm_summarizer.summarize_module.call_count == 1:
        print("SUCCESS: Regeneration triggered by hash change as expected.")
    else:
        print("FAILURE: Regeneration was not triggered by hash change.")

if __name__ == "__main__":
    asyncio.run(test_summary_regeneration())
