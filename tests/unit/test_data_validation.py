import pytest

from src.utils.data_validation import sanitize_symbol_data, truncate_string, validate_symbol_data


def test_truncate_string_rejects_non_positive_max_length() -> None:
    with pytest.raises(ValueError, match="max_length must be positive"):
        truncate_string("abc", 0)


def test_sanitize_symbol_data_truncates_known_fields_without_mutating_input() -> None:
    original = {
        "name": "x" * 1200,
        "fully_qualified_name": "y" * 2100,
        "return_type": "z" * 1200,
        "untouched": "keep-me",
    }

    sanitized = sanitize_symbol_data(original)

    assert len(sanitized["name"]) == 1000
    assert len(sanitized["fully_qualified_name"]) == 2000
    assert len(sanitized["return_type"]) == 1000
    assert sanitized["untouched"] == "keep-me"
    # Ensure original input remains unchanged
    assert len(original["name"]) == 1200


def test_validate_symbol_data_rejects_non_integer_and_non_positive_lines() -> None:
    valid, errors = validate_symbol_data(
        {
            "name": "Symbol",
            "start_line": "10",
            "end_line": 0,
        }
    )

    assert not valid
    assert "start_line must be an integer" in " | ".join(errors)
    assert "end_line must be >= 1" in " | ".join(errors)


def test_validate_symbol_data_rejects_inverted_line_range() -> None:
    valid, errors = validate_symbol_data(
        {
            "name": "Symbol",
            "start_line": 20,
            "end_line": 10,
        }
    )

    assert not valid
    assert any("cannot be greater than" in err for err in errors)
