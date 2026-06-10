"""
Checker service for single post analysis.
Provides policy caching and post checking logic shared between CLI and API.
"""
import logging
from typing import Optional

from core.models import PostData
from core.policy_loader import load_policies
from core.judge import judge

logger = logging.getLogger("policyguard.services.checker")


class CheckerService:
    """
    Service for checking posts against platform policies.
    Caches policies in memory for efficient batch processing.
    """
    
    def __init__(self):
        self._policy_cache: dict[str, str] = {}
        logger.info("CheckerService initialized")
    
    def get_policies(self, platform: str) -> str:
        """
        Load policies for a platform with caching.
        
        Args:
            platform: Platform name (reddit, x, tiktok, facebook, instagram)
            
        Returns:
            Concatenated policy text for the platform
        """
        if platform not in self._policy_cache:
            logger.info(f"Loading policies for platform: {platform}")
            self._policy_cache[platform] = load_policies(platform)
            policy_len = len(self._policy_cache[platform])
            logger.info(f"Cached {platform} policies ({policy_len:,} chars)")
        return self._policy_cache[platform]
    
    def warm_cache(self, platforms: set[str]) -> None:
        """
        Pre-load policies for multiple platforms.
        
        Args:
            platforms: Set of platform names to cache
        """
        logger.info(f"Warming policy cache for {len(platforms)} platform(s)...")
        for platform in platforms:
            self.get_policies(platform)
        logger.info(f"Policy cache warmed: {list(self._policy_cache.keys())}")
    
    def clear_cache(self) -> None:
        """Clear the policy cache."""
        logger.info("Clearing policy cache")
        self._policy_cache.clear()
    
    def check_post(
        self, 
        post: PostData, 
        video_transcript: Optional[str] = None
    ) -> dict:
        """
        Check a single post against platform policies.
        
        Args:
            post: PostData object with post content
            video_transcript: Optional pre-transcribed video audio
            
        Returns:
            Verdict as a dictionary
        """
        logger.debug(f"Checking post for {post.platform}: {post.url[:50]}...")
        policies = self.get_policies(post.platform)
        verdict = judge(post, policies, video_transcript)
        logger.debug(f"Verdict: {verdict.verdict} (confidence: {verdict.confidence})")
        return verdict.to_dict()
