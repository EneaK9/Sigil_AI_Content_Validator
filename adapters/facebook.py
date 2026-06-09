"""
Facebook adapter - returns not-supported error.
Facebook posts cannot be reliably scraped without authentication.
"""
from adapters.base import BaseAdapter
from core.models import PostData, NotSupportedError


class FacebookAdapter(BaseAdapter):
    """
    Adapter for Facebook posts.
    
    Facebook cannot be reliably scraped without authentication.
    This adapter immediately raises a NotSupportedError with instructions
    for using the --text flag instead.
    """
    
    def fetch(self, url: str) -> PostData:
        """
        Always raises NotSupportedError for Facebook URLs.
        
        Args:
            url: Facebook post URL (not used)
            
        Raises:
            NotSupportedError: Always, with instructions for manual text input
        """
        raise NotSupportedError(
            "Facebook posts cannot be automatically scraped due to Meta's authentication\n"
            "walls. To check a Facebook post, use the --text flag:\n\n"
            '  python policyguard.py check --platform facebook --text "paste post text here"'
        )
