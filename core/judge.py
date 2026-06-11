"""
Claude judge for policy compliance analysis.
Sends post content and platform policies to Claude API and parses the verdict.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

import anthropic

from config import CLAUDE_MODEL, CLAUDE_MAX_TOKENS, DEBUG_DIR, PREFERRED_MAX_IMAGES
from core.models import PostData, Violation, Warning, Verdict, JudgmentError, ScrapingError
from core.image_fetcher import fetch_image_as_base64
from core.video_transcriber import transcribe_video


SYSTEM_PROMPT = """You are an aggressive content auditor. Your job is to find problems.

## YOUR MINDSET
- Assume the worst possible interpretation of any content
- If something COULD be problematic, it IS worth flagging
- Consider how the most sensitive possible audience would react
- Look for hidden meanings, dog whistles, coded language, historical context
- If you have to think twice about whether something is okay, it's not okay — flag it
- Better to over-flag than to miss something
- Intent doesn't matter. Impact does. Even accidental harm is harm.

## WHAT YOU'RE LOOKING FOR
- Racism (overt, subtle, systemic, coded, historical, microaggressions)
- Antisemitism (tropes, dog whistles, conspiracy-adjacent language, "elites" rhetoric)
- Islamophobia, xenophobia, any form of ethnic/religious prejudice
- Sexism, misogyny, toxic masculinity
- Homophobia, transphobia, any LGBTQ+ hostility
- Ableism (using "crazy", "insane", "lame" as pejoratives)
- Classism, ageism
- Cultural appropriation, insensitivity, erasure
- Harmful stereotypes, even "positive" ones
- Microaggressions, tone policing, gaslighting
- Power imbalances, punching down
- Anything that could make any marginalized group uncomfortable

## THREE VERDICTS
- CLEAR_VIOLATION: Content clearly violates platform policies
- POSSIBLE_VIOLATION: You found SOMETHING problematic but it's not a clear policy violation
- PASS: Genuinely clean (this should be rare — most content has something if you look)

## RULES
1. Return ONLY raw JSON. No markdown fences. No explanation. No preamble.
   The first character of your response must be '{' and the last must be '}'.
2. For violations, quote the specific phrase and cite the exact policy section.
3. For warnings, explain what's problematic and why it matters.
4. When in doubt, flag it as POSSIBLE_VIOLATION. Over-flagging is better than under-flagging.
5. "It was a joke" is not a defense. Flag it anyway.
6. A post can have both violations AND warnings — list everything you find.
7. If images are provided, analyze them with the same aggressive scrutiny.
8. If a video transcript is provided, analyze it with the same aggressive scrutiny.
9. If an [Account Analysis] block is present showing BOT verdict, note this amplifies risk."""


def build_bot_context(post: PostData) -> str:
    """
    Build account analysis context from bot detection results.
    
    Args:
        post: PostData object with optional bot_score
        
    Returns:
        Formatted bot context string, or empty string if no bot analysis
    """
    if not post.bot_score:
        return ""
    
    from core.bot_detector import BotVerdict
    
    score = post.bot_score
    if score.verdict == BotVerdict.UNKNOWN:
        return ""
    
    triggered = [s for s in score.signals if s.triggered]
    signal_summary = "; ".join(s.evidence for s in triggered[:5])
    
    return f"""

[Account Analysis]
Bot Verdict: {score.verdict.value} (confidence: {score.confidence:.0%})
Score: {score.score} across {len(triggered)} signals
Key signals: {signal_summary}
"""


def build_user_prompt(post: PostData, policies_text: str, transcript_text: str = "") -> str:
    """
    Build the user prompt for Claude with post content and policies.
    
    Args:
        post: PostData object with the post to analyze
        policies_text: Concatenated policy markdown text
        transcript_text: Optional video transcript text to append
        
    Returns:
        Formatted user prompt string
    """
    # Build bot context if available
    bot_context = build_bot_context(post)
    
    prompt = f"""PLATFORM: {post.platform}

POST URL: {post.url}
POST AUTHOR: {post.author}
POST TITLE: {post.title}
POST TEXT:
---
{post.text}
---{bot_context}

PLATFORM POLICIES (Community Guidelines + Terms of Service):
---
{policies_text}
---

YOUR MISSION: Find problems. Look for any angle.

Analyze this content aggressively. Consider:
- How could this hurt someone from a marginalized group?
- What's the worst interpretation of this content?
- Is there historical/cultural context that makes this problematic?
- Even if the intent seems good, what's the impact?

Return a JSON object with this exact structure:

{{
  "verdict": "PASS" | "POSSIBLE_VIOLATION" | "CLEAR_VIOLATION",
  "violations": [
    {{
      "rule": "exact rule name from the policy",
      "severity": "HIGH" | "MEDIUM" | "LOW",
      "explanation": "why this is a clear violation",
      "policy_reference": "exact section name from the policy document",
      "quote": "verbatim phrase from the post that violates this rule"
    }}
  ],
  "warnings": [
    {{
      "category": "type of issue (racism, sexism, antisemitism, microaggression, etc.)",
      "risk_level": "OBVIOUS" | "INTERPRETIVE" | "DEEP_READ",
      "explanation": "what's wrong with this — be detailed",
      "problematic_element": "exact phrase or element that's problematic",
      "affected_groups": ["who could be harmed or offended"],
      "why_it_matters": "educational context — why this matters even if subtle"
    }}
  ],
  "passed_checks": ["list of policy categories that were checked and passed"],
  "confidence": 0.0 to 1.0,
  "recommendation": "what should be changed or removed, empty string if PASS"
}}

Rules:
- If violations is non-empty → verdict must be "CLEAR_VIOLATION"
- If violations is empty but warnings is non-empty → verdict must be "POSSIBLE_VIOLATION"
- If both empty → verdict is "PASS" (but look harder — PASS should be rare)
- When in doubt, flag it. Over-flagging is better than missing something."""
    
    return prompt + transcript_text


def fetch_video_transcripts(post: PostData) -> str:
    """
    Transcribe each video URL. Returns a formatted string to append
    to the prompt, or empty string if nothing was transcribed.
    
    Args:
        post: PostData object with video_urls
        
    Returns:
        Formatted transcript text or empty string
    """
    if not post.video_urls:
        return ""
    
    transcripts: list[str] = []
    
    for i, video_url in enumerate(post.video_urls, 1):
        transcript = transcribe_video(video_url)
        if transcript:
            transcripts.append(f"[Video {i} transcript]\n{transcript}")
    
    if not transcripts:
        return ""
    
    return "\n\n" + "\n\n".join(transcripts)


def build_message_content(
    post: PostData, 
    policies_text: str,
    provided_transcript: Optional[str] = None
) -> Union[str, list[dict]]:
    """
    Build message content for Claude, optionally including images.
    
    If no images: returns plain text string (current behavior)
    If images: returns list of content blocks with images and text
    
    Args:
        post: PostData object with the post to analyze
        policies_text: Concatenated policy markdown text
        provided_transcript: Optional pre-transcribed video text (bypasses Whisper)
        
    Returns:
        Either a string (text only) or list of content blocks (multimodal)
    """
    # Use provided transcript or fetch from video URLs
    if provided_transcript:
        transcript_text = f"\n\n[Video transcript]\n{provided_transcript}"
    else:
        transcript_text = fetch_video_transcripts(post)
    
    prompt_text = build_user_prompt(post, policies_text, transcript_text)
    
    # If no images, return plain text (maintains backward compatibility)
    if not post.image_urls:
        return prompt_text
    
    # Build multimodal content with images
    content_blocks: list[dict] = []
    skipped_images: list[str] = []
    
    # Fetch and add images (up to PREFERRED_MAX_IMAGES)
    for i, image_url in enumerate(post.image_urls[:PREFERRED_MAX_IMAGES]):
        try:
            base64_data, media_type = fetch_image_as_base64(image_url)
            content_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64_data
                }
            })
        except ScrapingError as e:
            skipped_images.append(f"Image {i+1}: {str(e)[:100]}")
    
    # If all images failed, fall back to text-only
    if not content_blocks:
        if skipped_images:
            prompt_text += f"\n\n[Note: {len(skipped_images)} image(s) could not be loaded for analysis]"
        return prompt_text
    
    # Add note about skipped images if any
    if skipped_images:
        prompt_text += f"\n\n[Note: {len(skipped_images)} image(s) could not be loaded: {'; '.join(skipped_images)}]"
    
    # Add note about additional images if we truncated
    if len(post.image_urls) > PREFERRED_MAX_IMAGES:
        prompt_text += f"\n\n[Note: Post contains {len(post.image_urls)} images, only first {PREFERRED_MAX_IMAGES} analyzed]"
    
    # Add the text prompt as the final block
    content_blocks.append({
        "type": "text",
        "text": prompt_text
    })
    
    return content_blocks


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
    required_fields = ["verdict", "violations", "warnings", "passed_checks", "confidence", "recommendation"]
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
    
    # Parse warnings
    warnings: list[Warning] = []
    for w in data["warnings"]:
        try:
            warnings.append(Warning(
                category=w.get("category", "Unknown"),
                risk_level=w.get("risk_level", "INTERPRETIVE"),
                explanation=w.get("explanation", ""),
                problematic_element=w.get("problematic_element", ""),
                affected_groups=w.get("affected_groups", []),
                why_it_matters=w.get("why_it_matters", "")
            ))
        except ValueError as e:
            raise JudgmentError(
                f"Invalid warning data from Claude: {e}"
            )
    
    try:
        verdict = Verdict(
            verdict=data["verdict"],
            platform=post.platform,
            post_url=post.url,
            post_text=post.text,
            violations=violations,
            warnings=warnings,
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


def judge(
    post: PostData, 
    policies_text: str,
    provided_transcript: Optional[str] = None
) -> Verdict:
    """
    Send post and policies to Claude for policy compliance analysis.
    
    Args:
        post: PostData object with the post to analyze
        policies_text: Concatenated policy markdown text
        provided_transcript: Optional pre-transcribed video text (bypasses Whisper API)
        
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
    
    # Build message content (text-only or multimodal with images)
    message_content = build_message_content(post, policies_text, provided_transcript)
    
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": message_content}]
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
