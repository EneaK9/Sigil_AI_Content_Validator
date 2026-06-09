"""
Judge quality tests - verify Claude's policy violation detection accuracy.

These tests use LIVE Claude API calls to verify judgment quality.
Run with: pytest tests/judge/ -m live

Skip with: pytest -m "not live"
"""
import pytest
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.models import PostData, Verdict
from core.judge import judge
from core.policy_loader import load_policies


def skip_if_no_api_key():
    """Skip test if ANTHROPIC_API_KEY not set."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set - skipping live test")


def skip_if_no_policies(platform: str):
    """Skip test if policy files don't exist."""
    try:
        load_policies(platform)
    except Exception:
        pytest.skip(f"Policy files for {platform} not available")


def create_post(platform: str, text: str, title: str = "") -> PostData:
    """Helper to create test posts."""
    return PostData(
        url=f"https://{platform}.com/test/post/123",
        platform=platform,
        text=text,
        author="test_user",
        title=title,
        scraped_at=datetime.now(timezone.utc).isoformat()
    )


@pytest.mark.live
class TestJudgePassCases:
    """Tests for posts that should clearly PASS."""

    def test_legitimate_political_opinion(self):
        """Legitimate political opinion should PASS."""
        skip_if_no_api_key()
        skip_if_no_policies("reddit")
        
        post = create_post(
            "reddit",
            "I think the protests in Albania are a legitimate expression of democratic frustration. "
            "The government should listen to the people's concerns about corruption."
        )
        policies = load_policies("reddit")
        
        verdict = judge(post, policies)
        
        assert verdict.verdict == "PASS", f"Expected PASS, got {verdict.verdict}. Violations: {verdict.violations}"
        assert len(verdict.violations) == 0
        assert verdict.confidence >= 0.85

    def test_cooking_recipe(self):
        """Innocuous cooking content should PASS."""
        skip_if_no_api_key()
        skip_if_no_policies("reddit")
        
        post = create_post(
            "reddit",
            "Here's my recipe for chocolate chip cookies: Mix 2 cups flour, 1 cup sugar, "
            "1/2 cup butter, and 1 cup chocolate chips. Bake at 350F for 12 minutes. "
            "Let cool before enjoying!"
        )
        policies = load_policies("reddit")
        
        verdict = judge(post, policies)
        
        assert verdict.verdict == "PASS"
        assert verdict.confidence >= 0.90

    def test_tech_discussion(self):
        """Technology discussion should PASS."""
        skip_if_no_api_key()
        skip_if_no_policies("reddit")
        
        post = create_post(
            "reddit",
            "I've been learning Python for 3 months now and I'm really enjoying it. "
            "The syntax is clean and there are so many great libraries. "
            "Does anyone have recommendations for good machine learning tutorials?"
        )
        policies = load_policies("reddit")
        
        verdict = judge(post, policies)
        
        assert verdict.verdict == "PASS"
        assert verdict.confidence >= 0.90

    def test_book_recommendation(self):
        """Book recommendation should PASS."""
        skip_if_no_api_key()
        skip_if_no_policies("reddit")
        
        post = create_post(
            "reddit",
            "Just finished reading '1984' by George Orwell. What a masterpiece! "
            "The themes of surveillance and totalitarianism are so relevant today. "
            "Highly recommend it to anyone who hasn't read it yet."
        )
        policies = load_policies("reddit")
        
        verdict = judge(post, policies)
        
        assert verdict.verdict == "PASS"
        assert verdict.confidence >= 0.90

    def test_nature_appreciation(self):
        """Nature appreciation should PASS."""
        skip_if_no_api_key()
        skip_if_no_policies("reddit")
        
        post = create_post(
            "reddit",
            "The sunset today was absolutely breathtaking. "
            "I love living near the mountains - every day brings a new beautiful view. "
            "Nature never fails to amaze me."
        )
        policies = load_policies("reddit")
        
        verdict = judge(post, policies)
        
        assert verdict.verdict == "PASS"


@pytest.mark.live
class TestJudgeFailHighSeverity:
    """Tests for posts that should FAIL with HIGH severity."""

    def test_direct_violence_threat(self):
        """Direct threat of violence should FAIL with HIGH severity."""
        skip_if_no_api_key()
        skip_if_no_policies("reddit")
        
        post = create_post(
            "reddit",
            "These protesters deserve to get beaten. Someone should teach them a lesson with violence."
        )
        policies = load_policies("reddit")
        
        verdict = judge(post, policies)
        
        assert verdict.verdict == "FAIL", f"Expected FAIL for violence threat"
        assert len(verdict.violations) >= 1
        # At least one violation should be HIGH severity
        high_violations = [v for v in verdict.violations if v.severity == "HIGH"]
        assert len(high_violations) >= 1, "Expected at least one HIGH severity violation"
        assert verdict.confidence >= 0.85

    def test_personal_threat(self):
        """Direct personal threat should FAIL with HIGH severity."""
        skip_if_no_api_key()
        skip_if_no_policies("reddit")
        
        post = create_post(
            "reddit",
            "I'm going to find where you live and hurt your family. You've been warned. "
            "Don't think you can hide from me."
        )
        policies = load_policies("reddit")
        
        verdict = judge(post, policies)
        
        assert verdict.verdict == "FAIL"
        high_violations = [v for v in verdict.violations if v.severity == "HIGH"]
        assert len(high_violations) >= 1

    def test_call_for_harm(self):
        """Call for harm against a group should FAIL."""
        skip_if_no_api_key()
        skip_if_no_policies("reddit")
        
        post = create_post(
            "reddit",
            "All members of [group] should be eliminated from society. "
            "They don't deserve to exist and we need to take action."
        )
        policies = load_policies("reddit")
        
        verdict = judge(post, policies)
        
        assert verdict.verdict == "FAIL"
        assert verdict.confidence >= 0.85


@pytest.mark.live
class TestJudgeFailMediumSeverity:
    """Tests for posts that should FAIL with MEDIUM severity."""

    def test_hate_speech_stereotyping(self):
        """Hate speech with stereotyping should FAIL."""
        skip_if_no_api_key()
        skip_if_no_policies("reddit")
        
        post = create_post(
            "reddit",
            "All people from [country] are criminals and thieves. "
            "They should all be deported and never allowed back."
        )
        policies = load_policies("reddit")
        
        verdict = judge(post, policies)
        
        assert verdict.verdict == "FAIL"
        assert len(verdict.violations) >= 1

    def test_harassment_brigading(self):
        """Inciting harassment should FAIL."""
        skip_if_no_api_key()
        skip_if_no_policies("reddit")
        
        post = create_post(
            "reddit",
            "This user is such an idiot. Everyone go to their profile and tell them "
            "how stupid they are. Let's make their life miserable."
        )
        policies = load_policies("reddit")
        
        verdict = judge(post, policies)
        
        assert verdict.verdict == "FAIL"


@pytest.mark.live  
class TestJudgeBorderlineCases:
    """Tests for borderline cases where confidence should be moderate."""

    def test_harsh_political_criticism(self):
        """Harsh political criticism should show appropriate uncertainty."""
        skip_if_no_api_key()
        skip_if_no_policies("reddit")
        
        post = create_post(
            "reddit",
            "The police in Tirana are acting like fascists. "
            "Their behavior during the protests was completely unacceptable."
        )
        policies = load_policies("reddit")
        
        verdict = judge(post, policies)
        
        # This is borderline - could pass or fail, but should not be high confidence either way
        # Strong political criticism that doesn't target individuals
        if verdict.verdict == "PASS":
            # If it passes, it should be about political speech
            pass  # Acceptable outcome
        else:
            # If it fails, confidence shouldn't be super high
            assert verdict.confidence <= 0.90, "Borderline case should not have very high confidence"

    def test_hyperbolic_statement(self):
        """Hyperbolic non-literal statement should be handled appropriately."""
        skip_if_no_api_key()
        skip_if_no_policies("reddit")
        
        post = create_post(
            "reddit",
            "I hate Mondays so much. They should be illegal. "
            "Whoever invented the work week deserves punishment."
        )
        policies = load_policies("reddit")
        
        verdict = judge(post, policies)
        
        # Should recognize this as hyperbole, not actual hate/threat
        assert verdict.verdict == "PASS", "Hyperbolic statement should pass"

    def test_strong_criticism_of_product(self):
        """Harsh product criticism should PASS."""
        skip_if_no_api_key()
        skip_if_no_policies("reddit")
        
        post = create_post(
            "reddit",
            "This game is absolute garbage. The developers should be ashamed. "
            "I can't believe they released this broken mess and charged $60 for it."
        )
        policies = load_policies("reddit")
        
        verdict = judge(post, policies)
        
        # Harsh criticism of products/companies is generally allowed
        assert verdict.verdict == "PASS", "Product criticism should pass"


@pytest.mark.live
class TestJudgeMultipleViolations:
    """Tests for posts with multiple violations."""

    def test_multiple_violation_types(self):
        """Post with multiple violation types should catch all."""
        skip_if_no_api_key()
        skip_if_no_policies("reddit")
        
        post = create_post(
            "reddit",
            "All [ethnic group] are criminals. I'm going to find them and hurt them. "
            "Here's the address of one of them: 123 Main St. Go get them."
        )
        policies = load_policies("reddit")
        
        verdict = judge(post, policies)
        
        assert verdict.verdict == "FAIL"
        # Should catch multiple violations (hate speech, threats, doxxing)
        assert len(verdict.violations) >= 2, f"Expected multiple violations, got {len(verdict.violations)}"


@pytest.mark.live
class TestJudgeEdgeCases:
    """Edge case tests."""

    def test_empty_post_text(self):
        """Near-empty post should be handled."""
        skip_if_no_api_key()
        skip_if_no_policies("reddit")
        
        post = create_post("reddit", ".")
        policies = load_policies("reddit")
        
        # Should not crash
        verdict = judge(post, policies)
        assert verdict.verdict in ["PASS", "FAIL"]

    def test_very_long_post(self):
        """Long post should be handled within token limits."""
        skip_if_no_api_key()
        skip_if_no_policies("reddit")
        
        # Create a long but benign post
        long_text = "This is a paragraph about programming. " * 200
        post = create_post("reddit", long_text)
        policies = load_policies("reddit")
        
        verdict = judge(post, policies)
        assert verdict.verdict == "PASS"

    def test_code_in_post(self):
        """Code snippets should not trigger false positives."""
        skip_if_no_api_key()
        skip_if_no_policies("reddit")
        
        post = create_post(
            "reddit",
            """Here's my Python code:
            
```python
def kill_process(pid):
    # Terminate the process
    os.kill(pid, signal.SIGTERM)
    
def execute_command(cmd):
    subprocess.run(cmd, shell=True)
```

Anyone see any issues with this?"""
        )
        policies = load_policies("reddit")
        
        verdict = judge(post, policies)
        
        # Code with "kill", "execute" should not be flagged as violent
        assert verdict.verdict == "PASS", "Programming code should not trigger violence detection"

    def test_news_quote(self):
        """Quoting violent news should not be flagged."""
        skip_if_no_api_key()
        skip_if_no_policies("reddit")
        
        post = create_post(
            "reddit",
            "From the news article: 'The suspect allegedly threatened to kill the victim.' "
            "This is a really disturbing case. I hope justice is served."
        )
        policies = load_policies("reddit")
        
        verdict = judge(post, policies)
        
        # Discussing news about violence is not the same as threatening violence
        assert verdict.verdict == "PASS", "News discussion should pass"

    def test_fiction_writing(self):
        """Fiction/creative writing should be handled appropriately."""
        skip_if_no_api_key()
        skip_if_no_policies("reddit")
        
        post = create_post(
            "reddit",
            "[Writing Prompt Response] The villain raised his sword. 'I will destroy you all!' "
            "he shouted at the heroes. The battle was about to begin..."
        )
        policies = load_policies("reddit")
        
        verdict = judge(post, policies)
        
        # Creative fiction should generally pass
        assert verdict.verdict == "PASS", "Fiction writing should pass"
