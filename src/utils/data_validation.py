"""
Data validation and sanitization utilities.

This module provides utilities for validating and sanitizing data
before database insertion to prevent truncation errors and data integrity issues.
"""

from typing import Optional, Any
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


def truncate_string(
    value: Optional[str],
    max_length: int,
    field_name: str = "field",
    log_truncation: bool = True
) -> Optional[str]:
    """
    Safely truncate a string to a maximum length.
    
    Args:
        value: String value to truncate
        max_length: Maximum allowed length
        field_name: Name of the field (for logging)
        log_truncation: Whether to log when truncation occurs
        
    Returns:
        Truncated string or None if input is None
    """
    if value is None:
        return None
    
    if len(value) <= max_length:
        return value
    
    truncated = value[:max_length]
    
    if log_truncation:
        logger.warning(
            "string_truncated",
            field_name=field_name,
            original_length=len(value),
            max_length=max_length,
            truncated_preview=truncated[:100] + "..." if len(truncated) > 100 else truncated
        )
    
    return truncated


def sanitize_symbol_data(symbol_data: dict) -> dict:
    """
    Sanitize symbol data before database insertion.
    
    This function ensures all string fields are within their maximum lengths
    as defined in the database schema.
    
    Args:
        symbol_data: Dictionary containing symbol data
        
    Returns:
        Sanitized dictionary with truncated fields
    """
    # Define max lengths based on database schema
    max_lengths = {
        'name': 1000,
        'fully_qualified_name': 2000,
        'return_type': 1000,
    }
    
    sanitized = symbol_data.copy()
    
    for field, max_length in max_lengths.items():
        if field in sanitized and isinstance(sanitized[field], str):
            sanitized[field] = truncate_string(
                sanitized[field],
                max_length,
                field_name=field
            )
    
    return sanitized


def validate_symbol_data(symbol_data: dict) -> tuple[bool, list[str]]:
    """
    Validate symbol data before database insertion.
    
    Args:
        symbol_data: Dictionary containing symbol data
        
    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors = []
    
    # Check required fields
    required_fields = ['name', 'start_line', 'end_line']
    for field in required_fields:
        if field not in symbol_data or symbol_data[field] is None:
            errors.append(f"Missing required field: {field}")
    
    # Validate line numbers
    if 'start_line' in symbol_data and 'end_line' in symbol_data:
        if symbol_data['start_line'] is not None and symbol_data['end_line'] is not None:
            if symbol_data['start_line'] > symbol_data['end_line']:
                errors.append(
                    f"start_line ({symbol_data['start_line']}) cannot be greater than "
                    f"end_line ({symbol_data['end_line']})"
                )
    
    return len(errors) == 0, errors

