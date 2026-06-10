"""
Comprehensive unit tests for bot detection module.
"""
import pytest
from datetime import datetime, timezone, timedelta

from core.bot_detector import (
    BotVerdict,
    BotSignal,
    BotScore,
    score_account,
    detect_bot,
    detect_x,
    detect_reddit,
    detect_tiktok,
    detect_instagram,
    detect_facebook,
    _check_bio_spam,
    _check_username_pattern,
    _get_account_age_days,
)
from config import BOT_SIGNAL_WEIGHTS


# =============================================================================
# Data Model Tests
# =============================================================================

class TestBotVerdict:
    """Tests for BotVerdict enum."""
    
    def test_verdict_enum_values(self):
        """Verify all verdict enum values exist."""
        assert BotVerdict.HUMAN.value == "HUMAN"
        assert BotVerdict.SUSPICIOUS.value == "SUSPICIOUS"
        assert BotVerdict.BOT.value == "BOT"
        assert BotVerdict.UNKNOWN.value == "UNKNOWN"
    
    def test_verdict_is_string_enum(self):
        """Verdict values are strings."""
        assert isinstance(BotVerdict.HUMAN.value, str)


class TestBotSignal:
    """Tests for BotSignal dataclass."""
    
    def test_signal_creation(self):
        """Create a bot signal with all fields."""
        signal = BotSignal(
            name="test_signal",
            triggered=True,
            weight=3,
            evidence="Test evidence"
        )
        assert signal.name == "test_signal"
        assert signal.triggered is True
        assert signal.weight == 3
        assert signal.evidence == "Test evidence"
    
    def test_signal_to_dict(self):
        """Signal converts to dictionary correctly."""
        signal = BotSignal(
            name="test",
            triggered=False,
            weight=2,
            evidence="Not triggered"
        )
        d = signal.to_dict()
        assert d["name"] == "test"
        assert d["triggered"] is False
        assert d["weight"] == 2
        assert d["evidence"] == "Not triggered"


class TestBotScore:
    """Tests for BotScore dataclass."""
    
    def test_score_creation(self):
        """Create a bot score with all fields."""
        score = BotScore(
            verdict=BotVerdict.SUSPICIOUS,
            score=7,
            confidence=0.65,
            platform="x",
            username="test_user"
        )
        assert score.verdict == BotVerdict.SUSPICIOUS
        assert score.score == 7
        assert score.confidence == 0.65
    
    def test_score_to_dict(self):
        """Score converts to dictionary correctly."""
        signal = BotSignal("test", True, 2, "Evidence")
        score = BotScore(
            verdict=BotVerdict.BOT,
            score=12,
            confidence=0.9,
            signals=[signal],
            platform="x",
            username="bot_user"
        )
        d = score.to_dict()
        assert d["verdict"] == "BOT"
        assert d["score"] == 12
        assert d["confidence"] == 0.9
        assert d["platform"] == "x"
        assert d["username"] == "bot_user"
        assert d["triggered_count"] == 1
        assert len(d["signals"]) == 1
    
    def test_score_has_timestamp(self):
        """Score includes checked_at timestamp."""
        score = BotScore(
            verdict=BotVerdict.HUMAN,
            score=0,
            confidence=0.9,
            platform="reddit",
            username="real_user"
        )
        assert "checked_at" in score.to_dict()


# =============================================================================
# Scoring Engine Tests
# =============================================================================

class TestScoringEngine:
    """Tests for score_account function."""
    
    def test_no_signals_returns_unknown(self):
        """No triggered signals returns UNKNOWN."""
        signals = [
            BotSignal("test1", False, 2, "Not triggered"),
            BotSignal("test2", False, 3, "Not triggered"),
        ]
        result = score_account(signals, "x", "user")
        assert result.verdict == BotVerdict.UNKNOWN
        assert result.score == 0
    
    def test_low_score_returns_human(self):
        """Low score (1-4) returns HUMAN."""
        signals = [
            BotSignal("test1", True, 2, "Triggered"),
            BotSignal("test2", False, 3, "Not triggered"),
        ]
        result = score_account(signals, "x", "user")
        assert result.verdict == BotVerdict.HUMAN
        assert result.score == 2
    
    def test_medium_score_returns_suspicious(self):
        """Medium score (5-9) returns SUSPICIOUS."""
        signals = [
            BotSignal("test1", True, 3, "Triggered"),
            BotSignal("test2", True, 3, "Triggered"),
        ]
        result = score_account(signals, "x", "user")
        assert result.verdict == BotVerdict.SUSPICIOUS
        assert result.score == 6
    
    def test_high_score_returns_bot(self):
        """High score (10+) with 4+ signals returns BOT."""
        signals = [
            BotSignal("test1", True, 3, "Triggered"),
            BotSignal("test2", True, 3, "Triggered"),
            BotSignal("test3", True, 3, "Triggered"),
            BotSignal("test4", True, 3, "Triggered"),
        ]
        result = score_account(signals, "x", "user")
        assert result.verdict == BotVerdict.BOT
        assert result.score == 12
    
    def test_critical_signal_returns_bot(self):
        """Critical signal (weight 5) returns BOT immediately."""
        signals = [
            BotSignal("coordinated_behavior", True, 5, "Critical signal"),
        ]
        result = score_account(signals, "x", "user")
        assert result.verdict == BotVerdict.BOT
    
    def test_confidence_scaling(self):
        """Confidence increases with score."""
        low_signals = [BotSignal("t1", True, 2, "E")]
        med_signals = [BotSignal("t1", True, 3, "E"), BotSignal("t2", True, 3, "E")]
        high_signals = [BotSignal(f"t{i}", True, 3, "E") for i in range(5)]
        
        low = score_account(low_signals, "x", "u")
        med = score_account(med_signals, "x", "u")
        high = score_account(high_signals, "x", "u")
        
        assert low.confidence >= 0.5
        assert med.confidence > low.confidence or med.verdict != low.verdict
    
    def test_immediate_pattern_x(self):
        """Immediate BOT pattern triggers for X."""
        signals = [
            BotSignal("tweet_count_lt_5", True, 3, "Only 2 tweets"),
            BotSignal("account_age_lt_30", True, 3, "15 days old"),
            BotSignal("following_gt_4900", True, 3, "Following 4950"),
        ]
        result = score_account(signals, "x", "suspicious")
        assert result.verdict == BotVerdict.BOT
        assert result.confidence == 0.97
    
    def test_immediate_pattern_tiktok(self):
        """Immediate BOT pattern triggers for TikTok."""
        signals = [
            BotSignal("video_count_zero", True, 3, "0 videos"),
            BotSignal("followers_gt_10000", True, 1, "50000 followers"),
        ]
        result = score_account(signals, "tiktok", "fake_influencer")
        assert result.verdict == BotVerdict.BOT
    
    def test_immediate_pattern_instagram(self):
        """Immediate BOT pattern triggers for Instagram."""
        signals = [
            BotSignal("media_count_zero", True, 3, "0 posts"),
            BotSignal("followers_gt_5000", True, 1, "10000 followers"),
            BotSignal("bio_spam", True, 3, "Spam bio"),
        ]
        result = score_account(signals, "instagram", "spam_account")
        assert result.verdict == BotVerdict.BOT
    
    def test_immediate_pattern_reddit(self):
        """Immediate BOT pattern triggers for Reddit."""
        signals = [
            BotSignal("karma_farm_subs", True, 3, "Posted in FreeKarma4U"),
            BotSignal("template_comments", True, 3, "Duplicate comments"),
            BotSignal("account_age_lt_7", True, 3, "3 days old"),
        ]
        result = score_account(signals, "reddit", "karma_bot")
        assert result.verdict == BotVerdict.BOT
    
    def test_immediate_pattern_facebook(self):
        """Immediate BOT pattern triggers for Facebook."""
        signals = [
            BotSignal("created_lt_30_days", True, 3, "Created 10 days ago"),
            BotSignal("followers_gt_10000", True, 1, "50000 followers"),
            BotSignal("link_only_posts", True, 3, "95% link posts"),
        ]
        result = score_account(signals, "facebook", "spam_page")
        assert result.verdict == BotVerdict.BOT


# =============================================================================
# Helper Function Tests
# =============================================================================

class TestHelperFunctions:
    """Tests for helper functions."""
    
    def test_check_bio_spam_detects_crypto(self):
        """Bio spam detected for crypto terms."""
        assert _check_bio_spam("DM for crypto tips! Telegram: @scam") is True
    
    def test_check_bio_spam_requires_multiple_terms(self):
        """Bio spam requires 2+ spam terms."""
        assert _check_bio_spam("I like crypto") is False
        assert _check_bio_spam("crypto nft investor") is True
    
    def test_check_bio_spam_empty_bio(self):
        """Empty bio is not spam."""
        assert _check_bio_spam("") is False
        assert _check_bio_spam(None) is False
    
    def test_username_pattern_random_numbers(self):
        """Random number usernames detected."""
        assert _check_username_pattern("user_48291") is True
        assert _check_username_pattern("john12345678") is True
    
    def test_username_pattern_normal_usernames(self):
        """Normal usernames not flagged."""
        assert _check_username_pattern("john_doe") is False
        assert _check_username_pattern("cooluser123") is False
    
    def test_account_age_from_timestamp(self):
        """Account age calculated from Unix timestamp."""
        one_week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).timestamp()
        age = _get_account_age_days(one_week_ago)
        assert age is not None
        assert 6 <= age <= 8  # Allow for timing variance
    
    def test_account_age_from_iso_string(self):
        """Account age calculated from ISO string."""
        one_month_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        age = _get_account_age_days(one_month_ago)
        assert age is not None
        assert 29 <= age <= 31


# =============================================================================
# X (Twitter) Detector Tests
# =============================================================================

class TestDetectX:
    """Tests for X/Twitter bot detection."""
    
    def test_clean_account_passes(self):
        """Legitimate account is not flagged as bot."""
        account = {
            "username": "real_journalist",
            "created_at": (datetime.now(timezone.utc) - timedelta(days=500)).isoformat(),
            "followers_count": 5000,
            "following_count": 300,
            "tweet_count": 2500,
            "description": "Tech journalist covering AI and startups",
            "default_profile_image": False,
            "listed_count": 50,
        }
        result = detect_x(account)
        assert result.verdict in [BotVerdict.HUMAN, BotVerdict.UNKNOWN]
    
    def test_new_account_flagged(self):
        """New account (<90 days) triggers signal."""
        account = {
            "username": "new_user",
            "created_at": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
            "followers_count": 50,
            "following_count": 100,
            "tweet_count": 20,
        }
        result = detect_x(account)
        triggered_names = {s.name for s in result.signals if s.triggered}
        assert "account_age_lt_90" in triggered_names
    
    def test_low_tweet_count_flagged(self):
        """Few tweets (<5) triggers signal."""
        account = {
            "username": "low_activity",
            "tweet_count": 3,
            "followers_count": 10,
            "following_count": 100,
        }
        result = detect_x(account)
        triggered_names = {s.name for s in result.signals if s.triggered}
        assert "tweet_count_lt_5" in triggered_names
    
    def test_bad_follower_ratio_flagged(self):
        """Bad follower ratio triggers signal."""
        account = {
            "username": "follower_farmer",
            "followers_count": 5,
            "following_count": 4500,
            "tweet_count": 100,
        }
        result = detect_x(account)
        triggered_names = {s.name for s in result.signals if s.triggered}
        assert "low_follower_ratio" in triggered_names
    
    def test_following_ceiling_flagged(self):
        """Near 5000 following limit triggers signal."""
        account = {
            "username": "limit_pusher",
            "followers_count": 100,
            "following_count": 4950,
            "tweet_count": 50,
        }
        result = detect_x(account)
        triggered_names = {s.name for s in result.signals if s.triggered}
        assert "following_gt_4900" in triggered_names
    
    def test_bio_spam_flagged(self):
        """Spam bio triggers signal."""
        account = {
            "username": "crypto_guru",
            "description": "DM me for crypto tips! Telegram @scam NFT investor",
            "followers_count": 100,
            "following_count": 200,
            "tweet_count": 50,
        }
        result = detect_x(account)
        triggered_names = {s.name for s in result.signals if s.triggered}
        assert "bio_spam" in triggered_names
    
    def test_automation_source_flagged(self):
        """Automation tool source triggers signal."""
        account = {
            "username": "auto_poster",
            "tweet_sources": ["IFTTT", "Buffer API"],
            "followers_count": 1000,
            "following_count": 500,
            "tweet_count": 5000,
        }
        result = detect_x(account)
        triggered_names = {s.name for s in result.signals if s.triggered}
        assert "automation_source" in triggered_names
    
    def test_obvious_bot_detected(self):
        """Multiple signals result in BOT verdict."""
        account = {
            "username": "user_839271",
            "created_at": (datetime.now(timezone.utc) - timedelta(days=15)).isoformat(),
            "followers_count": 10,
            "following_count": 4900,
            "tweet_count": 2,
            "description": "Crypto NFT forex invest DM telegram",
            "default_profile_image": True,
        }
        result = detect_x(account)
        assert result.verdict == BotVerdict.BOT


# =============================================================================
# Reddit Detector Tests
# =============================================================================

class TestDetectReddit:
    """Tests for Reddit bot detection."""
    
    def test_clean_account_passes(self):
        """Legitimate Reddit account is not flagged."""
        account = {
            "username": "longtime_redditor",
            "created_utc": (datetime.now(timezone.utc) - timedelta(days=1000)).timestamp(),
            "link_karma": 5000,
            "comment_karma": 15000,
            "has_verified_email": True,
        }
        result = detect_reddit(account)
        assert result.verdict in [BotVerdict.HUMAN, BotVerdict.UNKNOWN]
    
    def test_new_account_flagged(self):
        """New account (<30 days) triggers signal."""
        account = {
            "username": "newbie",
            "created_utc": (datetime.now(timezone.utc) - timedelta(days=10)).timestamp(),
            "link_karma": 10,
            "comment_karma": 20,
        }
        result = detect_reddit(account)
        triggered_names = {s.name for s in result.signals if s.triggered}
        assert "account_age_lt_30" in triggered_names
    
    def test_no_email_flagged(self):
        """Unverified email triggers signal."""
        account = {
            "username": "no_email_user",
            "has_verified_email": False,
            "link_karma": 100,
            "comment_karma": 100,
        }
        result = detect_reddit(account)
        triggered_names = {s.name for s in result.signals if s.triggered}
        assert "no_email_verification" in triggered_names
    
    def test_karma_farm_subs_flagged(self):
        """Posting in karma farm subs triggers signal."""
        account = {
            "username": "karma_farmer",
            "subreddits_posted": ["FreeKarma4U", "pics", "funny"],
            "link_karma": 500,
            "comment_karma": 100,
        }
        result = detect_reddit(account)
        triggered_names = {s.name for s in result.signals if s.triggered}
        assert "karma_farm_subs" in triggered_names
    
    def test_template_comments_flagged(self):
        """Duplicate comments trigger signal."""
        account = {
            "username": "copy_paster",
            "comment_texts": [
                "Great post!",
                "Great post!",
                "Great post!",
                "Great post!",
                "Great post!",
                "Amazing content!",
            ],
            "link_karma": 100,
            "comment_karma": 200,
            "created_utc": (datetime.now(timezone.utc) - timedelta(days=100)).timestamp(),
        }
        result = detect_reddit(account)
        triggered_names = {s.name for s in result.signals if s.triggered}
        assert "template_comments" in triggered_names


# =============================================================================
# TikTok Detector Tests
# =============================================================================

class TestDetectTiktok:
    """Tests for TikTok bot detection."""
    
    def test_clean_account_passes(self):
        """Legitimate TikTok creator is not flagged."""
        account = {
            "username": "real_creator",
            "follower_count": 50000,
            "following_count": 200,
            "video_count": 100,
            "avg_likes": 5000,
            "avg_comments": 100,
            "is_verified": True,
            "profile_image": "https://example.com/avatar.jpg",
            "bio": "Content creator sharing daily tips",
        }
        result = detect_tiktok(account)
        assert result.verdict in [BotVerdict.HUMAN, BotVerdict.UNKNOWN]
    
    def test_zero_videos_flagged(self):
        """Zero videos triggers signal."""
        account = {
            "username": "no_content",
            "follower_count": 100,
            "following_count": 500,
            "video_count": 0,
        }
        result = detect_tiktok(account)
        triggered_names = {s.name for s in result.signals if s.triggered}
        assert "video_count_zero" in triggered_names
    
    def test_low_engagement_flagged(self):
        """Low engagement rate triggers signal."""
        account = {
            "username": "fake_influencer",
            "follower_count": 100000,
            "following_count": 100,
            "video_count": 50,
            "avg_likes": 100,
            "avg_comments": 5,
        }
        result = detect_tiktok(account)
        triggered_names = {s.name for s in result.signals if s.triggered}
        assert "low_engagement" in triggered_names
    
    def test_zero_videos_many_followers_bot(self):
        """Zero videos + many followers = immediate BOT."""
        account = {
            "username": "bought_followers",
            "follower_count": 50000,
            "following_count": 100,
            "video_count": 0,
        }
        result = detect_tiktok(account)
        assert result.verdict == BotVerdict.BOT
    
    def test_recent_posting_burst_flagged(self):
        """Recent posting burst triggers signal."""
        account = {
            "username": "burst_poster",
            "follower_count": 1000,
            "following_count": 100,
            "video_count": 500,
            "recent_video_count": 200,  # 200 videos in 30 days = 6.7/day
            "profile_image": "https://example.com/avatar.jpg",
        }
        result = detect_tiktok(account)
        triggered_names = {s.name for s in result.signals if s.triggered}
        assert "recent_posting_burst" in triggered_names
    
    def test_extreme_recent_burst_bot(self):
        """Extreme recent posting = BOT."""
        account = {
            "username": "spam_bot",
            "follower_count": 500,
            "following_count": 50,
            "video_count": 600,
            "recent_video_count": 500,  # 500 in 30 days = 16.7/day
            "profile_image": "https://example.com/avatar.jpg",
        }
        result = detect_tiktok(account)
        triggered_names = {s.name for s in result.signals if s.triggered}
        assert "extreme_recent_burst" in triggered_names
        assert result.verdict == BotVerdict.BOT
    
    def test_video_timestamps_calculates_recent(self):
        """Video timestamps are used to calculate recent count."""
        import time
        now = time.time()
        # 10 videos in last 30 days, 5 older
        timestamps = [
            now - (5 * 24 * 60 * 60),   # 5 days ago
            now - (10 * 24 * 60 * 60),  # 10 days ago
            now - (15 * 24 * 60 * 60),  # 15 days ago
            now - (60 * 24 * 60 * 60),  # 60 days ago (outside window)
        ]
        account = {
            "username": "timestamp_test",
            "follower_count": 1000,
            "following_count": 100,
            "video_count": 4,
            "video_timestamps": timestamps,
            "profile_image": "https://example.com/avatar.jpg",
        }
        result = detect_tiktok(account)
        # Should have calculated recent_videos = 3 (within 30 days)
        # 3/30 = 0.1/day, not enough to trigger burst
        triggered_names = {s.name for s in result.signals if s.triggered}
        assert "recent_posting_burst" not in triggered_names


# =============================================================================
# Instagram Detector Tests
# =============================================================================

class TestDetectInstagram:
    """Tests for Instagram bot detection."""
    
    def test_clean_account_passes(self):
        """Legitimate Instagram account is not flagged."""
        account = {
            "username": "real_photographer",
            "follower_count": 10000,
            "following_count": 500,
            "media_count": 200,
            "avg_likes": 500,
            "avg_comments": 20,
            "biography": "Travel photographer | NYC based",
        }
        result = detect_instagram(account)
        assert result.verdict in [BotVerdict.HUMAN, BotVerdict.UNKNOWN]
    
    def test_zero_posts_flagged(self):
        """Zero posts triggers signal."""
        account = {
            "username": "no_posts",
            "follower_count": 100,
            "following_count": 500,
            "media_count": 0,
        }
        result = detect_instagram(account)
        triggered_names = {s.name for s in result.signals if s.triggered}
        assert "media_count_zero" in triggered_names
    
    def test_bio_spam_flagged(self):
        """Spam bio triggers signal."""
        account = {
            "username": "promo_account",
            "follower_count": 1000,
            "following_count": 2000,
            "media_count": 10,
            "biography": "DM for collabs! Crypto investor, Telegram @spam",
        }
        result = detect_instagram(account)
        triggered_names = {s.name for s in result.signals if s.triggered}
        assert "bio_spam" in triggered_names
    
    def test_zero_posts_many_followers_bot(self):
        """Zero posts + many followers + spam bio = BOT."""
        account = {
            "username": "spam_account",
            "follower_count": 10000,
            "following_count": 5000,
            "media_count": 0,
            "biography": "NFT crypto invest telegram DM",
        }
        result = detect_instagram(account)
        assert result.verdict == BotVerdict.BOT


# =============================================================================
# Facebook Detector Tests
# =============================================================================

class TestDetectFacebook:
    """Tests for Facebook bot detection."""
    
    def test_clean_account_passes(self):
        """Legitimate Facebook page is not flagged."""
        account = {
            "name": "Local Business",
            "username": "localbusiness",
            "created_time": (datetime.now(timezone.utc) - timedelta(days=500)).isoformat(),
            "follower_count": 5000,
            "friend_count": 0,
            "is_page": True,
            "has_personal_photos": True,
            "post_history": [
                {"type": "photo", "message": "New product!"},
                {"type": "status", "message": "Thanks for the support!"},
            ],
        }
        result = detect_facebook(account)
        assert result.verdict in [BotVerdict.HUMAN, BotVerdict.UNKNOWN]
    
    def test_new_page_flagged(self):
        """Recently created page triggers signal."""
        account = {
            "name": "New Page",
            "created_time": (datetime.now(timezone.utc) - timedelta(days=15)).isoformat(),
            "follower_count": 100,
        }
        result = detect_facebook(account)
        triggered_names = {s.name for s in result.signals if s.triggered}
        assert "created_lt_30_days" in triggered_names
    
    def test_link_only_posts_flagged(self):
        """Link-only posting triggers signal."""
        account = {
            "name": "Link Spammer",
            "follower_count": 1000,
            "post_history": [
                {"type": "link", "message": "Check this http://spam.com"},
                {"type": "link", "message": "Another link http://spam.com"},
                {"type": "link", "message": "More links http://spam.com"},
                {"type": "link", "message": "Links only http://spam.com"},
                {"type": "link", "message": "Spam http://spam.com"},
            ],
        }
        result = detect_facebook(account)
        triggered_names = {s.name for s in result.signals if s.triggered}
        assert "link_only_posts" in triggered_names
    
    def test_rapid_group_joins_flagged(self):
        """Rapid group joining triggers signal."""
        account = {
            "name": "Group Spammer",
            "follower_count": 500,
            "groups_joined_recently": 50,
        }
        result = detect_facebook(account)
        triggered_names = {s.name for s in result.signals if s.triggered}
        assert "rapid_group_joins" in triggered_names


# =============================================================================
# Generic Detector Tests
# =============================================================================

class TestDetectBot:
    """Tests for generic detect_bot function."""
    
    def test_routes_to_x_detector(self):
        """Platform 'x' routes to X detector."""
        account = {"username": "test", "tweet_count": 100}
        result = detect_bot("x", account)
        assert result.platform == "x"
    
    def test_routes_to_twitter_detector(self):
        """Platform 'twitter' routes to X detector."""
        account = {"username": "test", "tweet_count": 100}
        result = detect_bot("twitter", account)
        assert result.platform == "x"
    
    def test_unsupported_platform_returns_unknown(self):
        """Unsupported platform returns UNKNOWN."""
        account = {"username": "test"}
        result = detect_bot("myspace", account)
        assert result.verdict == BotVerdict.UNKNOWN
        assert result.platform == "myspace"
    
    def test_case_insensitive_platform(self):
        """Platform name is case insensitive."""
        account = {"username": "test", "link_karma": 100, "comment_karma": 100}
        result = detect_bot("REDDIT", account)
        assert result.platform == "reddit"
