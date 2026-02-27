"""Unit tests for security masking helpers."""

from src.utils.security import SecurityValidator


def test_mask_sensitive_data_masks_short_values_fully():
    """Short secrets should be fully redacted."""
    assert SecurityValidator.mask_sensitive_data("abcd", visible_chars=4) == "****"
    assert SecurityValidator.mask_sensitive_data("abcdef", visible_chars=4) == "******"


def test_mask_sensitive_data_masks_long_values_middle_only():
    """Long secrets keep configured head/tail and redact middle."""
    assert SecurityValidator.mask_sensitive_data("abcdefghijkl", visible_chars=3) == "abc******jkl"


def test_mask_sensitive_data_handles_non_positive_visible_chars():
    """Invalid visible_chars should safely mask the whole value."""
    assert SecurityValidator.mask_sensitive_data("secret-token", visible_chars=0) == "************"
    assert SecurityValidator.mask_sensitive_data("secret-token", visible_chars=-1) == "************"
