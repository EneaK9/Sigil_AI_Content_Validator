"""
Instagram adapter - returns not-supported error.
Instagram posts cannot be reliably scraped without authentication.
"""
from adapters.base import BaseAdapter
from core.models import PostData, NotSupportedError


class InstagramAdapter(BaseAdapter):
    """
    Adapter for Instagram posts.
    
    Instagram cannot be reliably scraped without authentication.
    This adapter immediately raises a NotSupportedError with instructions
    for using the --text flag instead.
    """
    
    def fetch(self, url: str) -> PostData:
        """
        Always raises NotSupportedError for Instagram URLs.
        
        Args:
            url: Instagram post URL (not used)
            
        Raises:
            NotSupportedError: Always, with instructions for manual text input
        """
        raise NotSupportedError(
            "Instagram posts cannot be automatically scraped due to Meta's authentication\n"
            "walls. To check an Instagram post, use the --text flag:\n\n"
            '  python policyguard.py check --platform instagram --text "paste post text here"'
        )
