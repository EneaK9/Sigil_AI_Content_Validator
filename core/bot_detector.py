"""
Bot detection module for analyzing social media accounts.

Uses signal stacking to detect bot accounts across platforms.
No single signal is enough - bots are caught by converging signals.
"""
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any

from config import (
    BOT_SIGNAL_WEIGHTS,
    BOT_VERDICT_THRESHOLDS,
    BOT_IMMEDIATE_PATTERNS,
    BOT_BIO_SPAM_TERMS,
    REDDIT_KARMA_FARM_SUBS,
    BOT_AUTOMATION_SOURCES,
)

logger = logging.getLogger("policyguard.bot_detector")


class BotVerdict(str, Enum):
    """Bot detection verdict."""
    HUMAN = "HUMAN"
    SUSPICIOUS = "SUSPICIOUS"
    BOT = "BOT"
    UNKNOWN = "UNKNOWN"  # Not enough data to score


@dataclass
class BotSignal:
    """A single bot detection signal."""
    name: str
    triggered: bool
    weight: int  # 1=low, 2=medium, 3=high, 5=critical
    evidence: str  # Human-readable explanation

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "triggered": self.triggered,
            "weight": self.weight,
            "evidence": self.evidence,
        }


@dataclass
class BotScore:
    """Complete bot detection result."""
    verdict: BotVerdict
    score: int  # Raw accumulated weight
    confidence: float  # 0.0 - 1.0
    signals: List[BotSignal] = field(default_factory=list)
    platform: str = ""
    username: str = ""
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        triggered = [s for s in self.signals if s.triggered]
        return {
            "verdict": self.verdict.value,
            "score": self.score,
            "confidence": self.confidence,
            "platform": self.platform,
            "username": self.username,
            "signals": [s.to_dict() for s in self.signals],
            "triggered_count": len(triggered),
            "checked_at": self.checked_at,
        }


def score_account(signals: List[BotSignal], platform: str, username: str) -> BotScore:
    """
    Score an account based on triggered signals.
    
    Args:
        signals: List of BotSignal objects (triggered or not)
        platform: Platform name
        username: Account username
        
    Returns:
        BotScore with verdict and confidence
    """
    triggered = [s for s in signals if s.triggered]
    total_score = sum(s.weight for s in triggered)
    signal_count = len(triggered)
    triggered_names = {s.name for s in triggered}

    logger.debug(f"Scoring {username} on {platform}: {signal_count} signals, score={total_score}")

    # Check immediate bot patterns first
    for pattern in BOT_IMMEDIATE_PATTERNS.get(platform, []):
        if all(p in triggered_names for p in pattern):
            logger.info(f"[BOT] Immediate pattern match for {username}: {pattern}")
            return BotScore(
                verdict=BotVerdict.BOT,
                score=total_score,
                confidence=0.97,
                signals=signals,
                platform=platform,
                username=username,
            )

    # Check for critical signals
    has_critical = any(s.weight >= BOT_SIGNAL_WEIGHTS["critical"] for s in triggered)
    if has_critical:
        logger.info(f"[BOT] Critical signal detected for {username}")
        return BotScore(
            verdict=BotVerdict.BOT,
            score=total_score,
            confidence=0.95,
            signals=signals,
            platform=platform,
            username=username,
        )

    # Standard threshold scoring
    bot_threshold = BOT_VERDICT_THRESHOLDS["BOT"]
    suspicious_threshold = BOT_VERDICT_THRESHOLDS["SUSPICIOUS"]

    if total_score >= bot_threshold["min_score"] and signal_count >= bot_threshold["min_signals"]:
        verdict = BotVerdict.BOT
        confidence = min(0.95, 0.6 + (total_score / 30))
    elif total_score >= suspicious_threshold["min_score"] or signal_count >= suspicious_threshold["min_signals"]:
        verdict = BotVerdict.SUSPICIOUS
        confidence = min(0.75, 0.4 + (total_score / 20))
    elif signal_count == 0:
        verdict = BotVerdict.UNKNOWN
        confidence = 0.0
    else:
        verdict = BotVerdict.HUMAN
        confidence = max(0.5, 1.0 - (total_score / 15))

    logger.info(f"[{verdict.value}] {username} on {platform}: score={total_score}, signals={signal_count}, conf={confidence:.2f}")

    return BotScore(
        verdict=verdict,
        score=total_score,
        confidence=confidence,
        signals=signals,
        platform=platform,
        username=username,
    )


def _check_bio_spam(bio: str) -> bool:
    """Check if bio contains spam indicators."""
    if not bio:
        return False
    bio_lower = bio.lower()
    matches = sum(1 for term in BOT_BIO_SPAM_TERMS if term in bio_lower)
    return matches >= 2


def _check_username_pattern(username: str) -> bool:
    """Check if username matches bot patterns."""
    if not username:
        return False
    # Random alphanumeric: user_48291x, john12345678
    if re.match(r'^[a-z]+[_]?\d{4,}[a-z]?$', username.lower()):
        return True
    # Long random strings
    if len(username) >= 15 and re.match(r'^[a-z0-9_]+$', username.lower()):
        # Check for low letter variety (random strings often have this)
        unique_chars = len(set(username.lower().replace('_', '')))
        if unique_chars < len(username) / 3:
            return True
    return False


def _parse_datetime(dt_value: Any) -> Optional[datetime]:
    """Parse datetime from various formats."""
    if dt_value is None:
        return None
    if isinstance(dt_value, datetime):
        return dt_value
    if isinstance(dt_value, (int, float)):
        # Unix timestamp
        return datetime.fromtimestamp(dt_value, tz=timezone.utc)
    if isinstance(dt_value, str):
        # ISO format
        try:
            # Handle various ISO formats
            dt_str = dt_value.replace('Z', '+00:00')
            return datetime.fromisoformat(dt_str)
        except ValueError:
            pass
    return None


def _get_account_age_days(created_at: Any) -> Optional[int]:
    """Calculate account age in days."""
    created = _parse_datetime(created_at)
    if not created:
        return None
    now = datetime.now(timezone.utc)
    return (now - created).days


def _add_activity_signals(
    signals: List[BotSignal],
    account_data: Dict[str, Any],
    post_count_field: str = "post_count",
    comment_count_field: str = "comment_count",
) -> None:
    """
    Add universal activity-based bot signals to any platform.
    
    These signals catch:
    - Recent posting bursts (high activity in last 30 days)
    - High comment frequency (excessive commenting)
    - New account + high activity (suspicious combination)
    - Extreme automation patterns
    
    Args:
        signals: List to append signals to
        account_data: Account data dictionary
        post_count_field: Field name for total post count
        comment_count_field: Field name for total comment count
    """
    # Get activity data
    post_count = account_data.get(post_count_field, 0) or account_data.get("video_count", 0) or account_data.get("tweet_count", 0) or account_data.get("media_count", 0)
    recent_posts = account_data.get("recent_post_count") or account_data.get("recent_video_count") or account_data.get("posts_last_30_days", 0)
    recent_comments = account_data.get("recent_comment_count") or account_data.get("comments_last_30_days", 0)
    total_comments = account_data.get(comment_count_field, 0) or account_data.get("total_comments", 0)
    age_days = _get_account_age_days(account_data.get("created_at"))
    
    # Calculate from timestamps if provided
    post_timestamps = account_data.get("post_timestamps") or account_data.get("video_timestamps", [])
    comment_timestamps = account_data.get("comment_timestamps", [])
    
    if post_timestamps and not recent_posts:
        now = datetime.now(timezone.utc).timestamp()
        thirty_days_ago = now - (30 * 24 * 60 * 60)
        recent_posts = sum(1 for ts in post_timestamps if ts > thirty_days_ago)
    
    if comment_timestamps and not recent_comments:
        now = datetime.now(timezone.utc).timestamp()
        thirty_days_ago = now - (30 * 24 * 60 * 60)
        recent_comments = sum(1 for ts in comment_timestamps if ts > thirty_days_ago)
    
    # === RECENT POSTING BURST ===
    if recent_posts > 0:
        recent_posts_per_day = recent_posts / 30
        signals.append(BotSignal(
            name="recent_posting_burst",
            triggered=recent_posts_per_day > 5,
            weight=BOT_SIGNAL_WEIGHTS["high"],
            evidence=f"Recent burst: {recent_posts} posts in last 30 days ({recent_posts_per_day:.1f}/day)"
        ))
        signals.append(BotSignal(
            name="extreme_recent_burst",
            triggered=recent_posts_per_day > 15,
            weight=BOT_SIGNAL_WEIGHTS["critical"],
            evidence=f"Extreme posting: {recent_posts} posts in 30 days ({recent_posts_per_day:.1f}/day)"
        ))
    
    # === HIGH COMMENT FREQUENCY ===
    if recent_comments > 0:
        comments_per_day = recent_comments / 30
        signals.append(BotSignal(
            name="high_comment_frequency",
            triggered=comments_per_day > 20,
            weight=BOT_SIGNAL_WEIGHTS["high"],
            evidence=f"High commenting: {recent_comments} comments in 30 days ({comments_per_day:.1f}/day)"
        ))
        signals.append(BotSignal(
            name="extreme_comment_frequency",
            triggered=comments_per_day > 50,
            weight=BOT_SIGNAL_WEIGHTS["critical"],
            evidence=f"Extreme commenting: {recent_comments} comments in 30 days ({comments_per_day:.1f}/day)"
        ))
    
    # === LIFETIME COMMENT VOLUME ===
    if total_comments > 0 and age_days and age_days > 0:
        lifetime_comments_per_day = total_comments / age_days
        signals.append(BotSignal(
            name="high_lifetime_comments",
            triggered=lifetime_comments_per_day > 10,
            weight=BOT_SIGNAL_WEIGHTS["high"],
            evidence=f"High lifetime commenting: {total_comments} total ({lifetime_comments_per_day:.1f}/day avg)"
        ))
    
    # === NEW ACCOUNT + HIGH ACTIVITY ===
    if age_days is not None and age_days < 30:
        # New account with lots of posts
        if post_count > 50:
            signals.append(BotSignal(
                name="new_account_high_posts",
                triggered=True,
                weight=BOT_SIGNAL_WEIGHTS["high"],
                evidence=f"New account ({age_days} days) with {post_count} posts"
            ))
        
        # New account with lots of comments
        if total_comments > 100 or recent_comments > 50:
            signals.append(BotSignal(
                name="new_account_high_comments",
                triggered=True,
                weight=BOT_SIGNAL_WEIGHTS["high"],
                evidence=f"New account ({age_days} days) with many comments"
            ))
    
    # === LIFETIME POSTING RATE (if we have creation date) ===
    if age_days and age_days > 0 and post_count > 0:
        lifetime_posts_per_day = post_count / age_days
        signals.append(BotSignal(
            name="high_lifetime_posting",
            triggered=lifetime_posts_per_day > 5,
            weight=BOT_SIGNAL_WEIGHTS["high"],
            evidence=f"High lifetime posting: {post_count} posts in {age_days} days ({lifetime_posts_per_day:.1f}/day)"
        ))
        signals.append(BotSignal(
            name="extreme_lifetime_posting",
            triggered=lifetime_posts_per_day > 20,
            weight=BOT_SIGNAL_WEIGHTS["critical"],
            evidence=f"Extreme automation: {post_count} posts in {age_days} days ({lifetime_posts_per_day:.1f}/day)"
        ))


# =============================================================================
# Platform-Specific Detectors
# =============================================================================

def detect_x(account_data: Dict[str, Any]) -> BotScore:
    """
    Detect bot signals for X (Twitter) accounts.
    
    Expected account_data fields:
        - username, created_at, followers_count, following_count
        - tweet_count, description, default_profile_image
        - tweet_sources (list of source strings from tweets)
    """
    signals = []
    username = account_data.get("username", "unknown")
    
    # Account age < 90 days
    age_days = _get_account_age_days(account_data.get("created_at"))
    if age_days is not None:
        signals.append(BotSignal(
            name="account_age_lt_90",
            triggered=age_days < 90,
            weight=BOT_SIGNAL_WEIGHTS["medium"],
            evidence=f"Account is {age_days} days old"
        ))
        signals.append(BotSignal(
            name="account_age_lt_30",
            triggered=age_days < 30,
            weight=BOT_SIGNAL_WEIGHTS["high"],
            evidence=f"Account is only {age_days} days old (very new)"
        ))

    # Tweet count < 5
    tweet_count = account_data.get("tweet_count", 0)
    signals.append(BotSignal(
        name="tweet_count_lt_5",
        triggered=tweet_count < 5,
        weight=BOT_SIGNAL_WEIGHTS["high"],
        evidence=f"Only {tweet_count} total tweets"
    ))

    # Follower:following ratio
    followers = account_data.get("followers_count", 0)
    following = account_data.get("following_count", 1)
    ratio = followers / following if following > 0 else 0
    signals.append(BotSignal(
        name="low_follower_ratio",
        triggered=ratio < 0.1 and following > 100,
        weight=BOT_SIGNAL_WEIGHTS["high"],
        evidence=f"Follower:following ratio is {ratio:.2f} ({followers}/{following})"
    ))

    # Following near ceiling (5000)
    signals.append(BotSignal(
        name="following_gt_4900",
        triggered=following >= 4900,
        weight=BOT_SIGNAL_WEIGHTS["high"],
        evidence=f"Following {following} accounts (near platform ceiling)"
    ))

    # Bio spam
    bio = account_data.get("description", "")
    signals.append(BotSignal(
        name="bio_spam",
        triggered=_check_bio_spam(bio),
        weight=BOT_SIGNAL_WEIGHTS["high"],
        evidence="Bio contains spam indicators (crypto/telegram/etc.)"
    ))

    # No profile image
    has_default_image = account_data.get("default_profile_image", False)
    signals.append(BotSignal(
        name="no_profile_image",
        triggered=has_default_image,
        weight=BOT_SIGNAL_WEIGHTS["medium"],
        evidence="Using default profile image"
    ))

    # Username pattern
    signals.append(BotSignal(
        name="username_pattern",
        triggered=_check_username_pattern(username),
        weight=BOT_SIGNAL_WEIGHTS["medium"],
        evidence=f"Username '{username}' matches bot pattern"
    ))

    # Automation source
    sources = set(account_data.get("tweet_sources", []))
    auto_sources = sources & BOT_AUTOMATION_SOURCES
    signals.append(BotSignal(
        name="automation_source",
        triggered=bool(auto_sources),
        weight=BOT_SIGNAL_WEIGHTS["high"],
        evidence=f"Posts from automation tools: {auto_sources}" if auto_sources else "No automation detected"
    ))

    # Not listed by anyone (with age > 1 year)
    listed_count = account_data.get("listed_count", 0)
    if age_days and age_days > 365:
        signals.append(BotSignal(
            name="not_listed",
            triggered=listed_count == 0,
            weight=BOT_SIGNAL_WEIGHTS["medium"],
            evidence=f"Not listed by anyone despite being {age_days} days old"
        ))
    
    # Universal activity signals
    _add_activity_signals(signals, account_data, post_count_field="tweet_count")

    return score_account(signals, platform="x", username=username)


def detect_reddit(account_data: Dict[str, Any]) -> BotScore:
    """
    Detect bot signals for Reddit accounts.
    
    Expected account_data fields:
        - username, created_utc, link_karma, comment_karma
        - has_verified_email, icon_img, subreddits_posted (list)
        - comment_texts (list of comment strings for template detection)
    """
    signals = []
    username = account_data.get("username", "unknown")

    # Account age < 30 days
    age_days = _get_account_age_days(account_data.get("created_utc"))
    if age_days is not None:
        signals.append(BotSignal(
            name="account_age_lt_30",
            triggered=age_days < 30,
            weight=BOT_SIGNAL_WEIGHTS["medium"],
            evidence=f"Account is {age_days} days old"
        ))
        signals.append(BotSignal(
            name="account_age_lt_7",
            triggered=age_days < 7,
            weight=BOT_SIGNAL_WEIGHTS["high"],
            evidence=f"Account is only {age_days} days old (brand new)"
        ))

    # No email verification
    has_email = account_data.get("has_verified_email", True)
    signals.append(BotSignal(
        name="no_email_verification",
        triggered=not has_email,
        weight=BOT_SIGNAL_WEIGHTS["medium"],
        evidence="Email not verified"
    ))

    # Zero or negative karma
    link_karma = account_data.get("link_karma", 0)
    comment_karma = account_data.get("comment_karma", 0)
    total_karma = link_karma + comment_karma
    signals.append(BotSignal(
        name="low_karma",
        triggered=total_karma <= 0,
        weight=BOT_SIGNAL_WEIGHTS["medium"],
        evidence=f"Total karma is {total_karma}"
    ))

    # Karma imbalance (link only, no discussion)
    if link_karma > 100 and comment_karma < 10:
        signals.append(BotSignal(
            name="karma_imbalance",
            triggered=True,
            weight=BOT_SIGNAL_WEIGHTS["medium"],
            evidence=f"Link karma ({link_karma}) >> comment karma ({comment_karma})"
        ))

    # Karma farming subreddits
    subs_posted = [s.lower() for s in account_data.get("subreddits_posted", [])]
    karma_farm_matches = [s for s in subs_posted if s in REDDIT_KARMA_FARM_SUBS]
    signals.append(BotSignal(
        name="karma_farm_subs",
        triggered=bool(karma_farm_matches),
        weight=BOT_SIGNAL_WEIGHTS["high"],
        evidence=f"Posted in karma farming subs: {karma_farm_matches}" if karma_farm_matches else "No karma farming detected"
    ))

    # Template comments (check for high similarity)
    comments = account_data.get("comment_texts", [])
    if len(comments) >= 3:
        # Simple duplicate detection
        unique_comments = set(comments)
        duplicate_ratio = 1 - (len(unique_comments) / len(comments))
        signals.append(BotSignal(
            name="template_comments",
            triggered=duplicate_ratio > 0.5,
            weight=BOT_SIGNAL_WEIGHTS["high"],
            evidence=f"{duplicate_ratio:.0%} of comments are duplicates"
        ))

    # Username pattern
    signals.append(BotSignal(
        name="username_pattern",
        triggered=_check_username_pattern(username),
        weight=BOT_SIGNAL_WEIGHTS["medium"],
        evidence=f"Username '{username}' matches bot pattern"
    ))

    # Default avatar
    icon_img = account_data.get("icon_img", "")
    is_default = "default" in icon_img.lower() if icon_img else True
    signals.append(BotSignal(
        name="default_avatar",
        triggered=is_default,
        weight=BOT_SIGNAL_WEIGHTS["low"],
        evidence="Using default Reddit avatar"
    ))
    
    # Universal activity signals
    _add_activity_signals(signals, account_data, post_count_field="link_karma", comment_count_field="total_comments")

    return score_account(signals, platform="reddit", username=username)


def detect_tiktok(account_data: Dict[str, Any]) -> BotScore:
    """
    Detect bot signals for TikTok accounts.
    
    Expected account_data fields:
        - username, follower_count, following_count, video_count
        - like_count, bio, profile_image, is_verified
        - avg_views, avg_likes, avg_comments (for engagement calc)
    """
    signals = []
    username = account_data.get("username", "unknown")

    # Zero videos
    video_count = account_data.get("video_count", 0)
    signals.append(BotSignal(
        name="video_count_zero",
        triggered=video_count == 0,
        weight=BOT_SIGNAL_WEIGHTS["high"],
        evidence="Account has zero videos (exists only to engage)"
    ))

    # Follower:following ratio
    followers = account_data.get("follower_count", 0)
    following = account_data.get("following_count", 1)
    ratio = followers / following if following > 0 else 0
    signals.append(BotSignal(
        name="low_follower_ratio",
        triggered=ratio < 0.05 and following > 100,
        weight=BOT_SIGNAL_WEIGHTS["high"],
        evidence=f"Follower:following ratio is {ratio:.3f} ({followers}/{following})"
    ))

    # Many followers threshold for immediate patterns
    signals.append(BotSignal(
        name="followers_gt_10000",
        triggered=followers > 10000,
        weight=BOT_SIGNAL_WEIGHTS["low"],  # Only high when combined with zero videos
        evidence=f"Has {followers:,} followers"
    ))

    # Unverified with massive following
    is_verified = account_data.get("is_verified", False)
    if not is_verified and followers > 100000 and video_count == 0:
        signals.append(BotSignal(
            name="unverified_mass_followers",
            triggered=True,
            weight=BOT_SIGNAL_WEIGHTS["high"],
            evidence=f"Unverified account with {followers:,} followers and no content"
        ))

    # Low engagement rate (< 0.5%)
    avg_likes = account_data.get("avg_likes", 0)
    avg_comments = account_data.get("avg_comments", 0)
    if followers > 0 and video_count > 0:
        engagement_rate = ((avg_likes + avg_comments) / followers) * 100
        signals.append(BotSignal(
            name="low_engagement",
            triggered=engagement_rate < 0.5,
            weight=BOT_SIGNAL_WEIGHTS["high"],
            evidence=f"Engagement rate is {engagement_rate:.2f}% (< 0.5%)"
        ))

    # Bio spam
    bio = account_data.get("bio", "")
    signals.append(BotSignal(
        name="bio_spam",
        triggered=_check_bio_spam(bio),
        weight=BOT_SIGNAL_WEIGHTS["high"],
        evidence="Bio contains spam indicators"
    ))

    # No profile picture
    profile_image = account_data.get("profile_image", "")
    is_default = not profile_image or "default" in profile_image.lower()
    signals.append(BotSignal(
        name="no_profile_image",
        triggered=is_default,
        weight=BOT_SIGNAL_WEIGHTS["medium"],
        evidence="Using default profile image"
    ))
    
    # Universal activity signals (handles recent bursts, posting frequency, etc.)
    _add_activity_signals(signals, account_data, post_count_field="video_count")

    return score_account(signals, platform="tiktok", username=username)


def detect_instagram(account_data: Dict[str, Any]) -> BotScore:
    """
    Detect bot signals for Instagram accounts.
    
    Expected account_data fields:
        - username, follower_count, following_count, media_count
        - biography, profile_pic_url, is_verified, is_private
        - avg_likes, avg_comments (for engagement calc)
    """
    signals = []
    username = account_data.get("username", "unknown")

    # Zero or very few posts
    media_count = account_data.get("media_count", 0)
    signals.append(BotSignal(
        name="media_count_zero",
        triggered=media_count == 0,
        weight=BOT_SIGNAL_WEIGHTS["high"],
        evidence="Account has zero posts"
    ))
    signals.append(BotSignal(
        name="media_count_low",
        triggered=0 < media_count < 3,
        weight=BOT_SIGNAL_WEIGHTS["medium"],
        evidence=f"Account has only {media_count} posts"
    ))

    # Follower:following ratio
    followers = account_data.get("follower_count", 0)
    following = account_data.get("following_count", 1)
    ratio = followers / following if following > 0 else 0
    signals.append(BotSignal(
        name="low_follower_ratio",
        triggered=ratio < 0.1 and following > 100,
        weight=BOT_SIGNAL_WEIGHTS["high"],
        evidence=f"Follower:following ratio is {ratio:.2f} ({followers}/{following})"
    ))

    # Many followers threshold
    signals.append(BotSignal(
        name="followers_gt_5000",
        triggered=followers > 5000,
        weight=BOT_SIGNAL_WEIGHTS["low"],  # Only significant when combined
        evidence=f"Has {followers:,} followers"
    ))

    # Bio spam
    bio = account_data.get("biography", "") or account_data.get("bio", "")
    signals.append(BotSignal(
        name="bio_spam",
        triggered=_check_bio_spam(bio),
        weight=BOT_SIGNAL_WEIGHTS["high"],
        evidence="Bio contains spam indicators"
    ))

    # Low engagement rate
    avg_likes = account_data.get("avg_likes", 0)
    avg_comments = account_data.get("avg_comments", 0)
    if followers > 0 and media_count > 0:
        engagement_rate = ((avg_likes + avg_comments) / followers) * 100
        # Thresholds based on follower tier
        if followers < 1000:
            threshold = 5.0
        elif followers < 10000:
            threshold = 3.0
        elif followers < 100000:
            threshold = 2.0
        else:
            threshold = 1.0
        
        signals.append(BotSignal(
            name="low_engagement",
            triggered=engagement_rate < threshold * 0.2,  # < 20% of healthy
            weight=BOT_SIGNAL_WEIGHTS["high"],
            evidence=f"Engagement rate is {engagement_rate:.2f}% (expected >{threshold}%)"
        ))

    # Private + following thousands (follow/unfollow pattern)
    is_private = account_data.get("is_private", False)
    if is_private and following > 2000:
        signals.append(BotSignal(
            name="private_mass_following",
            triggered=True,
            weight=BOT_SIGNAL_WEIGHTS["medium"],
            evidence=f"Private account following {following:,} accounts"
        ))

    # Username pattern
    signals.append(BotSignal(
        name="username_pattern",
        triggered=_check_username_pattern(username),
        weight=BOT_SIGNAL_WEIGHTS["medium"],
        evidence=f"Username '{username}' matches bot pattern"
    ))
    
    # Universal activity signals
    _add_activity_signals(signals, account_data, post_count_field="media_count")

    return score_account(signals, platform="instagram", username=username)


def detect_facebook(account_data: Dict[str, Any]) -> BotScore:
    """
    Detect bot signals for Facebook accounts/pages.
    
    Expected account_data fields:
        - name, created_time (pages), follower_count, friend_count
        - about/bio, profile_picture, post_history (list of posts)
        - is_page, groups_joined_recently (count)
    """
    signals = []
    name = account_data.get("name", "unknown")
    username = account_data.get("username", name)

    # Account/Page creation date (mainly for pages)
    age_days = _get_account_age_days(account_data.get("created_time"))
    if age_days is not None:
        signals.append(BotSignal(
            name="created_lt_90_days",
            triggered=age_days < 90,
            weight=BOT_SIGNAL_WEIGHTS["medium"],
            evidence=f"Account created {age_days} days ago"
        ))
        signals.append(BotSignal(
            name="created_lt_30_days",
            triggered=age_days < 30,
            weight=BOT_SIGNAL_WEIGHTS["high"],
            evidence=f"Account created only {age_days} days ago"
        ))

    # Follower count thresholds
    followers = account_data.get("follower_count", 0)
    signals.append(BotSignal(
        name="followers_gt_10000",
        triggered=followers > 10000,
        weight=BOT_SIGNAL_WEIGHTS["low"],
        evidence=f"Has {followers:,} followers"
    ))

    # Few friends/followers (account exists only to post)
    friends = account_data.get("friend_count", 0)
    if not account_data.get("is_page", False):
        signals.append(BotSignal(
            name="few_friends",
            triggered=friends < 10,
            weight=BOT_SIGNAL_WEIGHTS["medium"],
            evidence=f"Only {friends} friends"
        ))

    # Link-only posts
    posts = account_data.get("post_history", [])
    if posts:
        link_posts = sum(1 for p in posts if p.get("type") == "link" or "http" in str(p.get("message", "")))
        link_ratio = link_posts / len(posts) if posts else 0
        signals.append(BotSignal(
            name="link_only_posts",
            triggered=link_ratio > 0.9 and len(posts) >= 5,
            weight=BOT_SIGNAL_WEIGHTS["high"],
            evidence=f"{link_ratio:.0%} of posts are external links"
        ))

    # Template comments
    comments = account_data.get("comment_texts", [])
    if len(comments) >= 3:
        unique_comments = set(comments)
        duplicate_ratio = 1 - (len(unique_comments) / len(comments))
        signals.append(BotSignal(
            name="template_comments",
            triggered=duplicate_ratio > 0.5,
            weight=BOT_SIGNAL_WEIGHTS["high"],
            evidence=f"{duplicate_ratio:.0%} of comments are duplicates"
        ))

    # Rapid group joins
    groups_joined = account_data.get("groups_joined_recently", 0)
    signals.append(BotSignal(
        name="rapid_group_joins",
        triggered=groups_joined > 20,
        weight=BOT_SIGNAL_WEIGHTS["high"],
        evidence=f"Joined {groups_joined} groups recently"
    ))

    # No personal photos
    has_personal_photos = account_data.get("has_personal_photos", True)
    signals.append(BotSignal(
        name="no_personal_photos",
        triggered=not has_personal_photos,
        weight=BOT_SIGNAL_WEIGHTS["high"],
        evidence="No personal photos, only promotional content"
    ))

    # Bio spam
    bio = account_data.get("about", "") or account_data.get("bio", "")
    signals.append(BotSignal(
        name="bio_spam",
        triggered=_check_bio_spam(bio),
        weight=BOT_SIGNAL_WEIGHTS["high"],
        evidence="Bio contains spam indicators"
    ))
    
    # Universal activity signals
    _add_activity_signals(signals, account_data, post_count_field="post_count")

    return score_account(signals, platform="facebook", username=username)


def detect_bot(platform: str, account_data: Dict[str, Any]) -> BotScore:
    """
    Detect bot signals for any supported platform.
    
    Args:
        platform: Platform name (x, reddit, tiktok, instagram, facebook)
        account_data: Dictionary of account data
        
    Returns:
        BotScore with verdict and signals
    """
    detectors = {
        "x": detect_x,
        "twitter": detect_x,
        "reddit": detect_reddit,
        "tiktok": detect_tiktok,
        "instagram": detect_instagram,
        "facebook": detect_facebook,
    }
    
    detector = detectors.get(platform.lower())
    if not detector:
        logger.warning(f"No bot detector for platform: {platform}")
        return BotScore(
            verdict=BotVerdict.UNKNOWN,
            score=0,
            confidence=0.0,
            signals=[],
            platform=platform,
            username=account_data.get("username", "unknown"),
        )
    
    return detector(account_data)
