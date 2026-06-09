"""
Platform detection from URLs.
Simple URL pattern matching to determine which social media platform a URL belongs to.
"""
from config import PLATFORM_PATTERNS


def detect_platform(url: str) -> str:
    """
    Detect the social media platform from a URL.
    
    Args:
        url: The URL to analyze
        
    Returns:
        Platform name string: "reddit", "x", "tiktok", "facebook", or "instagram"
        
    Raises:
        ValueError: If URL doesn't match any supported platform pattern,
                   with a message listing all supported patterns
    """
    url_lower = url.lower()
    
    for platform, patterns in PLATFORM_PATTERNS.items():
        for pattern in patterns:
            if pattern in url_lower:
                return platform
    
    # Build helpful error message with supported patterns
    supported = []
    for platform, patterns in PLATFORM_PATTERNS.items():
        pattern_list = ", ".join(patterns)
        supported.append(f"  {platform}: {pattern_list}")
    
    supported_str = "\n".join(supported)
    
    raise ValueError(
        f"Could not detect platform from URL: {url}\n\n"
        f"Supported URL patterns:\n{supported_str}\n\n"
        f"Make sure the URL contains one of the patterns above."
    )


def is_supported_platform(platform: str) -> bool:
    """
    Check if a platform name is supported.
    
    Args:
        platform: Platform name to check
        
    Returns:
        True if platform is supported, False otherwise
    """
    return platform in PLATFORM_PATTERNS


def get_supported_platforms() -> list[str]:
    """
    Get list of all supported platform names.
    
    Returns:
        List of platform name strings
    """
    return list(PLATFORM_PATTERNS.keys())
