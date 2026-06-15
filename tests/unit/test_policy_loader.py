"""Unit tests for sigil.validation.policy_loader."""
import pytest

from sigil.config import PLATFORM_POLICY_FILES, get_settings
from sigil.validation.models import PolicyNotFoundError
from sigil.validation.policy_loader import (
    get_policy_char_count,
    list_cached_policies,
    load_policies,
)


@pytest.fixture
def policies_dir(tmp_path, monkeypatch):
    """Point the settings policies_dir at an empty temp directory."""
    monkeypatch.setattr(get_settings(), "policies_dir", tmp_path)
    return tmp_path


class TestLoadPolicies:
    def test_load_bundled_reddit_policies(self):
        """The packaged policies should load for a real platform."""
        policies = load_policies("reddit")
        assert isinstance(policies, str)
        assert "reddit" in policies.lower()

    def test_invalid_platform_raises(self):
        with pytest.raises(ValueError, match="Unknown platform"):
            load_policies("youtube")

    def test_missing_file_raises(self, policies_dir):
        with pytest.raises(PolicyNotFoundError, match="not found"):
            load_policies("reddit")

    def test_empty_file_raises(self, policies_dir):
        (policies_dir / "reddit_content_policy.md").write_text("")
        (policies_dir / "reddit_user_agreement.md").write_text("content")
        with pytest.raises(PolicyNotFoundError, match="empty"):
            load_policies("reddit")

    def test_concatenates_files_with_headers(self, policies_dir):
        (policies_dir / "reddit_content_policy.md").write_text("Content policy text.")
        (policies_dir / "reddit_user_agreement.md").write_text("User agreement text.")
        policies = load_policies("reddit")
        assert "Content policy text." in policies
        assert "User agreement text." in policies
        assert "===" in policies

    @pytest.mark.parametrize(
        "platform", ["reddit", "x", "tiktok", "facebook", "instagram", "linkedin"]
    )
    def test_all_platforms_mapped(self, platform):
        assert len(PLATFORM_POLICY_FILES[platform]) >= 1


class TestPolicyHelpers:
    def test_char_count_positive(self):
        assert get_policy_char_count("reddit") > 0

    def test_list_cached_lists_existing(self, policies_dir):
        (policies_dir / "reddit_content_policy.md").write_text("x")
        result = list_cached_policies()
        assert "reddit_content_policy.md" in result["reddit"]
        assert "reddit_user_agreement.md" not in result["reddit"]
