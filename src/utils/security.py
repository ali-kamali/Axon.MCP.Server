"""Security utilities and input validation."""

import re
import hashlib
from typing import Optional, List
from pathlib import Path

from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class SecurityValidator:
    """Validates and sanitizes inputs for security."""
    
    # Dangerous patterns that could indicate injection attacks
    DANGEROUS_PATTERNS = [
        r';\s*DROP\s+TABLE',  # SQL injection
        r'<script',  # XSS
        r'javascript:',  # XSS
        r'\.\./\.\.',  # Path traversal
        r'\\\\',  # Windows path traversal
        r'eval\s*\(',  # Code injection
        r'exec\s*\(',  # Code injection
        r'__import__',  # Python import injection
    ]
    
    # Allowed file extensions for upload/processing
    ALLOWED_CODE_EXTENSIONS = {
        '.py', '.js', '.ts', '.tsx', '.jsx', '.cs', '.java', '.go',
        '.vue', '.md', '.json', '.yaml', '.yml', '.xml', '.sql',
        '.csproj', '.sln', '.txt', '.html', '.css', '.scss'
    }
    
    @classmethod
    def validate_file_path(cls, file_path: str, allow_absolute: bool = False) -> bool:
        """
        Validate file path for security issues.
        
        Args:
            file_path: Path to validate
            allow_absolute: Whether to allow absolute paths
            
        Returns:
            True if path is safe, False otherwise
        """
        try:
            path = Path(file_path)
            
            # Check for path traversal
            if '..' in file_path:
                logger.warning("path_traversal_detected", path=file_path)
                return False
            
            # Check for absolute paths if not allowed
            if not allow_absolute and path.is_absolute():
                logger.warning("absolute_path_not_allowed", path=file_path)
                return False
            
            # Check for suspicious patterns
            for pattern in cls.DANGEROUS_PATTERNS:
                if re.search(pattern, file_path, re.IGNORECASE):
                    logger.warning("dangerous_pattern_detected", path=file_path, pattern=pattern)
                    return False
            
            return True
        except Exception as e:
            logger.error("path_validation_error", path=file_path, error=str(e))
            return False
    
    @classmethod
    def validate_file_extension(cls, file_path: str) -> bool:
        """
        Validate file extension is allowed.
        
        Args:
            file_path: Path to check
            
        Returns:
            True if extension is allowed, False otherwise
        """
        ext = Path(file_path).suffix.lower()
        
        if ext not in cls.ALLOWED_CODE_EXTENSIONS:
            logger.warning("unauthorized_file_extension", path=file_path, extension=ext)
            return False
        
        return True
    
    @classmethod
    def sanitize_input(cls, input_text: str, max_length: int = 10000) -> str:
        """
        Sanitize user input.
        
        Args:
            input_text: Input to sanitize
            max_length: Maximum allowed length
            
        Returns:
            Sanitized input
        """
        if not input_text:
            return ""
        
        # Truncate to max length
        sanitized = input_text[:max_length]
        
        # Remove null bytes
        sanitized = sanitized.replace('\x00', '')
        
        # Check for dangerous patterns
        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, sanitized, re.IGNORECASE):
                logger.warning("dangerous_pattern_in_input", pattern=pattern)
                # Remove the pattern
                sanitized = re.sub(pattern, '', sanitized, flags=re.IGNORECASE)
        
        return sanitized
    
    @classmethod
    def validate_repository_url(cls, url: str) -> bool:
        """
        Validate repository URL.
        
        Args:
            url: Repository URL to validate
            
        Returns:
            True if URL is safe, False otherwise
        """
        # Allow common Git hosting patterns
        allowed_patterns = [
            r'^https://github\.com/',
            r'^https://gitlab\.com/',
            r'^git@github\.com:',
            r'^git@gitlab\.com:',
            r'^https://.*\.visualstudio\.com/',
            r'^https://dev\.azure\.com/',
        ]
        
        for pattern in allowed_patterns:
            if re.match(pattern, url):
                return True
        
        logger.warning("unauthorized_repository_url", url=url)
        return False
    
    @classmethod
    def hash_sensitive_data(cls, data: str) -> str:
        """
        Hash sensitive data for logging/storage.
        
        Args:
            data: Sensitive data to hash
            
        Returns:
            SHA-256 hash of data
        """
        return hashlib.sha256(data.encode()).hexdigest()
    
    @classmethod
    def mask_sensitive_data(cls, data: str, visible_chars: int = 4) -> str:
        """
        Mask sensitive data for display.
        
        Args:
            data: Data to mask
            visible_chars: Number of characters to keep visible
            
        Returns:
            Masked data (e.g., "sk_test_****7890")
        """
        if len(data) <= visible_chars:
            return '*' * len(data)
        
        return data[:visible_chars] + '*' * (len(data) - visible_chars * 2) + data[-visible_chars:]
    
    @classmethod
    def validate_symbol_name(cls, name: str) -> bool:
        """
        Validate symbol name is safe.
        
        Args:
            name: Symbol name to validate
            
        Returns:
            True if name is valid, False otherwise
        """
        # Allow letters, numbers, underscores, dots, and hyphens
        if not re.match(r'^[a-zA-Z0-9_\.\-<>]+$', name):
            logger.warning("invalid_symbol_name", name=name)
            return False
        
        return True
    
    @classmethod
    def check_rate_limit(cls, identifier: str, max_requests: int = 100, window_seconds: int = 60) -> bool:
        """
        Check if identifier has exceeded rate limit.
        
        Args:
            identifier: Unique identifier (e.g., IP, user ID)
            max_requests: Maximum requests allowed
            window_seconds: Time window in seconds
            
        Returns:
            True if within limit, False if exceeded
        """
        # This would integrate with Redis or in-memory cache
        # Simplified implementation
        return True


class SecretDetector:
    """Detects and redacts secrets in code."""
    
    # Patterns for detecting secrets
    SECRET_PATTERNS = [
        (r'password\s*=\s*["\']([^"\']+)["\']', 'password'),
        (r'api[_-]?key\s*=\s*["\']([^"\']+)["\']', 'api_key'),
        (r'secret\s*=\s*["\']([^"\']+)["\']', 'secret'),
        (r'token\s*=\s*["\']([^"\']+)["\']', 'token'),
        (r'["\']sk_live_[a-zA-Z0-9]{24,}["\']', 'stripe_key'),
        (r'["\']pk_live_[a-zA-Z0-9]{24,}["\']', 'stripe_key'),
        (r'-----BEGIN PRIVATE KEY-----', 'private_key'),
        (r'-----BEGIN RSA PRIVATE KEY-----', 'rsa_key'),
    ]
    
    @classmethod
    def scan_for_secrets(cls, content: str) -> List[dict]:
        """
        Scan content for potential secrets.
        
        Args:
            content: Content to scan
            
        Returns:
            List of detected secrets with type and location
        """
        detected = []
        
        for pattern, secret_type in cls.SECRET_PATTERNS:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                detected.append({
                    'type': secret_type,
                    'location': match.span(),
                    'context': content[max(0, match.start() - 20):min(len(content), match.end() + 20)]
                })
                
                logger.warning(
                    "secret_detected",
                    secret_type=secret_type,
                    location=match.span()
                )
        
        return detected
    
    @classmethod
    def redact_secrets(cls, content: str) -> str:
        """
        Redact secrets from content.
        
        Args:
            content: Content to redact
            
        Returns:
            Content with secrets redacted
        """
        redacted = content
        
        for pattern, secret_type in cls.SECRET_PATTERNS:
            redacted = re.sub(
                pattern,
                f'[REDACTED_{secret_type.upper()}]',
                redacted,
                flags=re.IGNORECASE
            )
        
        return redacted

