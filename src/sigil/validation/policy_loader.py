"""
Policy loader for reading cached policy Markdown files from disk.
"""
from sigil.config import PLATFORM_POLICY_FILES, get_settings
from sigil.validation.models import PolicyNotFoundError


def _number_lines(text: str) -> str:
    """Prefix each line with a right-aligned line number (restarts per document).

    This lets the report prosecutor cite exact policy lines (e.g. "line 16")
    the way a human compliance analyst would.
    """
    return "\n".join(
        f"{i:>4} | {line}" for i, line in enumerate(text.splitlines(), start=1)
    )


def load_policies(platform: str, *, numbered: bool = False) -> str:
    """
    Load all policy Markdown files for the given platform.
    
    Returns them concatenated as a single string with clear section headers.
    
    Args:
        platform: Platform name (reddit, x, tiktok, facebook, instagram)
        numbered: When True, prefix every policy line with its line number so a
            consumer (the report generator) can cite exact lines per document.
        
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

    policies_dir = get_settings().policies_dir
    policy_files = PLATFORM_POLICY_FILES[platform]
    sections: list[str] = []
    
    for filename in policy_files:
        filepath = policies_dir / filename
        
        if not filepath.exists():
            raise PolicyNotFoundError(
                f"Policy file '{filename}' not found in {policies_dir}."
            )
        
        content = filepath.read_text(encoding="utf-8")
        
        if not content.strip():
            raise PolicyNotFoundError(
                f"Policy file '{filename}' is empty ({filepath})."
            )
        
        # Create section header from filename
        section_name = filename.replace("_", " ").replace(".md", "").title()
        body = _number_lines(content) if numbered else content
        sections.append(f"=== {section_name} ===\n\n{body}")
    
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
    policies_dir = get_settings().policies_dir
    result: dict[str, list[str]] = {}
    
    for platform, files in PLATFORM_POLICY_FILES.items():
        cached = []
        for filename in files:
            filepath = policies_dir / filename
            if filepath.exists():
                cached.append(filename)
        result[platform] = cached
    
    return result
