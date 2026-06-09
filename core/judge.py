"""
Claude judge for policy compliance analysis.
Sends post content and platform policies to Claude API and parses the verdict.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from config import CLAUDE_MODEL, CLAUDE_MAX_TOKENS, DEBUG_DIR
from core.models import PostData, Violation, Verdict, JudgmentError


SYSTEM_PROMPT = """You are a precise, impartial social media policy compliance analyst.

Your job is to determine whether a given post violates the platform's
Community Guidelines or Terms of Service.

Rules you must follow:
1. Only flag genuine violations. Do not flag things that are merely
   controversial, edgy, or offensive but do not violate written policy.
2. Always quote the specific phrase from the post that triggered the violation.
3. Always cite the exact policy section or rule name, not a vague description.
4. Your confidence score must reflect genuine uncertainty — if the post is
   clearly fine, return 0.95+. If it is borderline, return 0.5-0.75.
5. Return ONLY raw JSON. No markdown fences. No explanation. No preamble.
   The first character of your response must be '{' and the last must be '}'."""


def build_user_prompt(post: PostData, policies_text: str) -> str:
    """
    Build the user prompt for Claude with post content and policies.
    
    Args:
        post: PostData object with the post to analyze
        policies_text: Concatenated policy markdown text
        
    Returns:
        Formatted user prompt string
    """
    return f"""PLATFORM: {post.platform}

POST URL: {post.url}
POST AUTHOR: {post.author}
POST TITLE: {post.title}
POST TEXT:
---
{post.text}
---

PLATFORM POLICIES (Community Guidelines + Terms of Service):
---
{policies_text}
---

Analyze the post against the policies above and return a JSON object with
this exact structure:

{{
  "verdict": "PASS" or "FAIL",
  "violations": [
    {{
      "rule": "exact rule name from the policy",
      "severity": "HIGH" | "MEDIUM" | "LOW",
      "explanation": "plain English explanation of why this is a violation",
      "policy_reference": "exact section name from the policy document",
      "quote": "verbatim phrase from the post that violates this rule"
    }}
  ],
  "passed_checks": ["list of policy categories that were checked and passed"],
  "confidence": 0.0 to 1.0,
  "recommendation": "what should be changed or removed, empty string if PASS"
}}

If the post passes all policies, violations must be an empty array []."""


def build_verdict(post: PostData, data: dict) -> Verdict:
    """
    Convert Claude's JSON response into a Verdict object.
    
    Args:
        post: Original PostData object
        data: Parsed JSON dict from Claude's response
        
    Returns:
        Verdict object
        
    Raises:
        JudgmentError: If response is missing required fields
    """
    required_fields = ["verdict", "violations", "passed_checks", "confidence", "recommendation"]
    missing = [f for f in required_fields if f not in data]
    if missing:
        raise JudgmentError(
            f"Claude response missing required fields: {', '.join(missing)}. "
            f"The model may have returned an incomplete response."
        )
    
    # Parse violations
    violations: list[Violation] = []
    for v in data["violations"]:
        try:
            violations.append(Violation(
                rule=v.get("rule", "Unknown"),
                severity=v.get("severity", "MEDIUM"),
                explanation=v.get("explanation", ""),
                policy_reference=v.get("policy_reference", ""),
                quote=v.get("quote", "")
            ))
        except ValueError as e:
            raise JudgmentError(
                f"Invalid violation data from Claude: {e}"
            )
    
    try:
        verdict = Verdict(
            verdict=data["verdict"],
            platform=post.platform,
            post_url=post.url,
            post_text=post.text,
            violations=violations,
            passed_checks=data["passed_checks"],
            confidence=float(data["confidence"]),
            recommendation=data.get("recommendation", ""),
            checked_at=datetime.now(timezone.utc).isoformat()
        )
    except ValueError as e:
        raise JudgmentError(
            f"Invalid verdict data from Claude: {e}"
        )
    
    return verdict


def judge(post: PostData, policies_text: str) -> Verdict:
    """
    Send post and policies to Claude for policy compliance analysis.
    
    Args:
        post: PostData object with the post to analyze
        policies_text: Concatenated policy markdown text
        
    Returns:
        Verdict object with the analysis result
        
    Raises:
        JudgmentError: If Claude API call fails or response cannot be parsed
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise JudgmentError(
            "ANTHROPIC_API_KEY environment variable is not set. "
            "Create a .env file with: ANTHROPIC_API_KEY=your-key-here"
        )
    
    client = anthropic.Anthropic(api_key=api_key)
    
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_user_prompt(post, policies_text)}]
        )
    except anthropic.APIError as e:
        raise JudgmentError(
            f"Claude API error: {e}. "
            f"Check your API key and internet connection."
        )
    
    raw = response.content[0].text.strip()
    
    # Try to parse JSON
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        # Save raw response for debugging
        DEBUG_DIR.mkdir(exist_ok=True)
        debug_file = DEBUG_DIR / "last_response.txt"
        debug_file.write_text(raw, encoding="utf-8")
        
        raise JudgmentError(
            f"Claude returned invalid JSON. Raw response saved to debug/last_response.txt\n"
            f"First 200 chars: {raw[:200]}\n"
            f"JSON parse error: {e}"
        )
    
    return build_verdict(post, data)
