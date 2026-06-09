"""
Unit tests for core/policy_loader.py - Policy loading from cache.
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.policy_loader import load_policies, get_policy_char_count, list_cached_policies
from core.models import PolicyNotFoundError
from config import POLICIES_DIR, PLATFORM_POLICY_FILES


class TestLoadPolicies:
    """Tests for load_policies function."""

    def test_load_reddit_policies(self):
        """Should load Reddit policies if files exist."""
        # This test uses actual policy files if they exist
        try:
            policies = load_policies("reddit")
            assert isinstance(policies, str)
            assert len(policies) > 0
            assert "Reddit" in policies or "reddit" in policies.lower()
        except PolicyNotFoundError:
            pytest.skip("Reddit policy files not present")

    def test_invalid_platform_raises_error(self):
        """Should raise ValueError for unknown platform."""
        with pytest.raises(ValueError) as exc_info:
            load_policies("youtube")
        assert "Unknown platform" in str(exc_info.value)
        assert "youtube" in str(exc_info.value)

    def test_missing_policy_file_raises_error(self, tmp_path, monkeypatch):
        """Should raise PolicyNotFoundError for missing files."""
        # Point to empty temp directory
        monkeypatch.setattr("core.policy_loader.POLICIES_DIR", tmp_path)
        
        with pytest.raises(PolicyNotFoundError) as exc_info:
            load_policies("reddit")
        
        assert "not found" in str(exc_info.value)
        assert "python policyguard.py refresh" in str(exc_info.value)

    def test_empty_policy_file_raises_error(self, tmp_path, monkeypatch):
        """Should raise PolicyNotFoundError for empty files."""
        monkeypatch.setattr("core.policy_loader.POLICIES_DIR", tmp_path)
        
        # Create empty policy files
        (tmp_path / "reddit_content_policy.md").write_text("")
        (tmp_path / "reddit_user_agreement.md").write_text("Some content")
        
        with pytest.raises(PolicyNotFoundError) as exc_info:
            load_policies("reddit")
        
        assert "empty" in str(exc_info.value)

    def test_concatenates_multiple_files(self, tmp_path, monkeypatch):
        """Should concatenate multiple policy files with headers."""
        monkeypatch.setattr("core.policy_loader.POLICIES_DIR", tmp_path)
        
        # Create test policy files
        (tmp_path / "reddit_content_policy.md").write_text("Content policy text here.")
        (tmp_path / "reddit_user_agreement.md").write_text("User agreement text here.")
        
        policies = load_policies("reddit")
        
        assert "Content policy text here." in policies
        assert "User agreement text here." in policies
        # Should have section headers
        assert "===" in policies

    @pytest.mark.parametrize("platform", ["reddit", "x", "tiktok", "facebook", "instagram"])
    def test_all_platforms_defined(self, platform):
        """All platforms should have policy file mappings."""
        assert platform in PLATFORM_POLICY_FILES
        assert len(PLATFORM_POLICY_FILES[platform]) >= 1


class TestGetPolicyCharCount:
    """Tests for get_policy_char_count function."""

    def test_returns_integer(self):
        """Should return integer character count."""
        try:
            count = get_policy_char_count("reddit")
            assert isinstance(count, int)
            assert count > 0
        except PolicyNotFoundError:
            pytest.skip("Reddit policy files not present")


class TestListCachedPolicies:
    """Tests for list_cached_policies function."""

    def test_returns_dict(self):
        """Should return dictionary of cached policies."""
        result = list_cached_policies()
        assert isinstance(result, dict)
        assert "reddit" in result
        assert "x" in result
        assert isinstance(result["reddit"], list)

    def test_lists_existing_files(self, tmp_path, monkeypatch):
        """Should only list files that exist."""
        monkeypatch.setattr("core.policy_loader.POLICIES_DIR", tmp_path)
        
        # Create only one of the Reddit files
        (tmp_path / "reddit_content_policy.md").write_text("test")
        
        result = list_cached_policies()
        
        assert "reddit_content_policy.md" in result["reddit"]
        assert "reddit_user_agreement.md" not in result["reddit"]
