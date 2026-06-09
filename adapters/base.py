"""
Abstract base class for platform adapters.
All platform-specific adapters must inherit from this class.
"""
from abc import ABC, abstractmethod

from core.models import PostData


class BaseAdapter(ABC):
    """
    Abstract base class that all platform adapters must inherit from.
    
    Each adapter is responsible for fetching post content from a specific
    social media platform and returning it as a PostData object.
    """
    
    @abstractmethod
    def fetch(self, url: str) -> PostData:
        """
        Fetch post content from the given URL.
        
        Args:
            url: The full URL to the social media post
            
        Returns:
            PostData object containing the post content
            
        Raises:
            ScrapingError: If the post cannot be fetched (HTTP errors, etc.)
            NotSupportedError: If the platform doesn't support auto-scraping
            
        Must NEVER return a PostData with an empty text field silently.
        If text cannot be extracted, must either:
        - Include a note in the text field explaining why
        - Raise an exception with a clear error message
        """
        pass
