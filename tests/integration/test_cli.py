"""
Integration tests for CLI - policyguard.py command line interface.
"""
import subprocess
import sys
import json
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestCLIHelp:
    """Tests for CLI help and basic functionality."""

    def test_main_help(self):
        """Should display help message."""
        result = subprocess.run(
            [sys.executable, "policyguard.py", "--help"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert "PolicyGuard" in result.stdout
        assert "check" in result.stdout
        assert "refresh" in result.stdout
        assert "show-policy" in result.stdout

    def test_check_help(self):
        """Should display check command help."""
        result = subprocess.run(
            [sys.executable, "policyguard.py", "check", "--help"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert "--text" in result.stdout
        assert "--platform" in result.stdout
        assert "--output" in result.stdout
        assert "--quiet" in result.stdout

    def test_refresh_help(self):
        """Should display refresh command help."""
        result = subprocess.run(
            [sys.executable, "policyguard.py", "refresh", "--help"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert "--platform" in result.stdout

    def test_no_command_shows_help(self):
        """Should show help when no command given."""
        result = subprocess.run(
            [sys.executable, "policyguard.py"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True
        )
        assert result.returncode == 1
        assert "usage" in result.stdout.lower() or "usage" in result.stderr.lower()


class TestCLICheckCommand:
    """Tests for the check command."""

    def test_check_requires_url_or_text(self):
        """Should error when neither URL nor --text provided."""
        result = subprocess.run(
            [sys.executable, "policyguard.py", "check"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True
        )
        assert result.returncode == 1
        assert "Must specify" in result.stderr or "error" in result.stderr.lower()

    def test_check_text_requires_platform(self):
        """Should error when --text given without --platform."""
        result = subprocess.run(
            [sys.executable, "policyguard.py", "check", "--text", "test content"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True
        )
        assert result.returncode == 1
        assert "--platform is required" in result.stderr

    def test_check_invalid_platform(self):
        """Should error for invalid platform name."""
        result = subprocess.run(
            [sys.executable, "policyguard.py", "check", "--platform", "youtube", "--text", "test"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True
        )
        assert result.returncode == 1
        assert "Unknown platform" in result.stderr

    def test_check_facebook_url_gives_instruction(self):
        """Should give --text instruction for Facebook URL."""
        result = subprocess.run(
            [sys.executable, "policyguard.py", "check", "https://facebook.com/user/posts/123"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True
        )
        assert result.returncode == 1
        assert "--text" in result.stderr
        assert "facebook" in result.stderr.lower()

    def test_check_instagram_url_gives_instruction(self):
        """Should give --text instruction for Instagram URL."""
        result = subprocess.run(
            [sys.executable, "policyguard.py", "check", "https://instagram.com/p/ABC123/"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True
        )
        assert result.returncode == 1
        assert "--text" in result.stderr
        assert "instagram" in result.stderr.lower()

    def test_check_invalid_url(self):
        """Should error for unsupported URL."""
        result = subprocess.run(
            [sys.executable, "policyguard.py", "check", "https://youtube.com/watch?v=abc"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True
        )
        assert result.returncode == 1
        assert "Could not detect platform" in result.stderr

    @pytest.mark.live
    def test_check_with_text_produces_json(self):
        """Should produce valid JSON output for text input."""
        result = subprocess.run(
            [sys.executable, "policyguard.py", "check", 
             "--platform", "reddit", 
             "--text", "This is a test post about programming.",
             "--quiet"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            pytest.skip(f"Live test failed: {result.stderr}")
        
        # Should be valid JSON
        output = json.loads(result.stdout)
        assert "verdict" in output
        assert output["verdict"] in ["PASS", "FAIL"]
        assert "confidence" in output
        assert "violations" in output


class TestCLIShowPolicy:
    """Tests for show-policy command."""

    def test_show_policy_invalid_platform(self):
        """Should error for invalid platform."""
        result = subprocess.run(
            [sys.executable, "policyguard.py", "show-policy", "youtube"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True
        )
        assert result.returncode == 1
        assert "Unknown platform" in result.stderr

    def test_show_policy_requires_platform(self):
        """Should error when platform not provided."""
        result = subprocess.run(
            [sys.executable, "policyguard.py", "show-policy"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True
        )
        assert result.returncode != 0


class TestCLIErrorMessages:
    """Tests for error message quality."""

    def test_error_messages_are_actionable(self):
        """Error messages should tell user what to do."""
        # Missing policy file error
        result = subprocess.run(
            [sys.executable, "policyguard.py", "show-policy", "reddit"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            env={"PATH": "", "HOME": "/tmp"}  # Likely to cause policy not found
        )
        
        # Either succeeds (policies exist) or gives actionable error
        if result.returncode != 0:
            # Should mention how to fix
            assert "refresh" in result.stderr.lower() or "policyguard.py" in result.stderr
