"""
Policy loader for reading cached policy Markdown files from disk.
"""
from pathlib import Path

from config import POLICIES_DIR, PLATFORM_POLICY_FILES
from core.models import PolicyNotFoundError


def load_policies(platform: str) -> str:
    """
    Load all policy Markdown files for the given platform.
    
    Returns them concatenated as a single string with clear section headers.
    
    Args:
        platform: Platform name (reddit, x, tiktok, facebook, instagram)
        
    Returns:
        Concatenated policy text with section headers
        
    Raises:
        PolicyNotFoundError: If any required policy file is missing
    """
    if platform not in PLATFORM_POLICY_FILES:
        raise ValueError(
            f"Unknown platform '{platform}'. "
            f"Supported platforms: {', '.join(PLATFORM_POLICY_FILES.keys())}"
        )
    
    policy_files = PLATFORM_POLICY_FILES[platform]
    sections: list[str] = []
    
    for filename in policy_files:
        filepath = POLICIES_DIR / filename
        
        if not filepath.exists():
            raise PolicyNotFoundError(
                f"Policy file '{filename}' not found.\n"
                f"Run: python policyguard.py refresh"
            )
        
        content = filepath.read_text(encoding="utf-8")
        
        if not content.strip():
            raise PolicyNotFoundError(
                f"Policy file '{filename}' is empty.\n"
                f"Run: python policyguard.py refresh"
            )
        
        # Create section header from filename
        section_name = filename.replace("_", " ").replace(".md", "").title()
        sections.append(f"=== {section_name} ===\n\n{content}")
    
    return "\n\n".join(sections)


def get_policy_char_count(platform: str) -> int:
    """
    Get the total character count of policies for a platform.
    
    Args:
        platform: Platform name
        
    Returns:
        Total character count
    """
    policies = load_policies(platform)
    return len(policies)


def list_cached_policies() -> dict[str, list[str]]:
    """
    List all cached policy files organized by platform.
    
    Returns:
        Dict mapping platform names to list of cached policy filenames
    """
    result: dict[str, list[str]] = {}
    
    for platform, files in PLATFORM_POLICY_FILES.items():
        cached = []
        for filename in files:
            filepath = POLICIES_DIR / filename
            if filepath.exists():
                cached.append(filename)
        result[platform] = cached
    
    return result
