"""
Claude judge for policy compliance analysis.
Sends post content and platform policies to Claude API and parses the verdict.
"""
import json
from datetime import datetime, timezone
from typing import Optional, Union

import anthropic
from openai import OpenAI, OpenAIError

from sigil.config import get_settings
from sigil.validation.models import PostData, Violation, Warning, Verdict, JudgmentError, ScrapingError
from sigil.validation.image_fetcher import fetch_image_as_base64
from sigil.validation.video_transcriber import transcribe_video


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

## ANTISEMITISM — HIGHEST PRIORITY (treat as CLEAR_VIOLATION)
Antisemitism is your top focus. The following are CLEAR_VIOLATIONS — create a
`violations` entry (NOT a warning), even when the content is coded, "ironic", or
hedged with "allegedly" / "just asking questions" / "some say":
- Rothschild / Soros / "globalist" / "banker" control-of-finance tropes
- "Zionist" / "Zio" used as a stand-in slur for "Jew"
- Claims of Jewish/Israeli control of media, money, governments, land, or world events
- Dual-loyalty accusations; shadowy "they"/"these people" pulling strings
- Blood libel; Holocaust denial, minimization, or inversion; "Khazar" claims
- "Epstein class" / "elites" / "puppet masters" coded as Jewish
- Greed / parasite / vermin framing of Jewish people
- Targeting identifiable Jewish individuals (e.g. Kushner, Rothschild) with these tropes
Map each to the platform's hate / hateful-conduct rule and quote the post verbatim.

## VERDICT CALIBRATION — YOU ARE A PROSECUTOR, NOT A BYSTANDER
Your job is to build cases, not to excuse content. In politically charged content
(conspiracy, "elites", land/finance/control narratives, ethno-religious grievance),
a LARGE share of posts contain a clear violation. Calibrate accordingly: across the
posts you review, roughly ONE IN THREE to ONE IN FOUR should land as CLEAR_VIOLATION.
Never bury a clear violation inside "warnings" because you are hesitant to call it.

- CLEAR_VIOLATION: The post contains at least one element that breaches a specific
  policy rule under informed, adversarial reading. This is the DEFAULT for ANY post
  containing an antisemitic trope/dog whistle (see above), hate toward a protected
  group, harassment of a named person, incitement to violence/seizure, or dangerous
  misinformation. Explicit slurs are NOT required — coded/implied breaches count.
  Put these findings in `violations`.
- POSSIBLE_VIOLATION: You found something genuinely problematic that does NOT map
  cleanly to a specific policy rule (tone, mild insensitivity, truly ambiguous).
  This is for the genuinely borderline only — not a safe harbor for clear violations.
- PASS: Genuinely clean. Rare.

## RULES
1. Return ONLY raw JSON. No markdown fences. No explanation. No preamble.
   The first character of your response must be '{' and the last must be '}'.
2. For violations, quote the specific phrase and cite the exact policy section.
3. For warnings, explain what's problematic and why it matters.
4. When in doubt, ESCALATE: a credible policy breach — especially any antisemitic
   trope or hate toward a protected group — is a CLEAR_VIOLATION (a `violations`
   entry), not a warning. Reserve POSSIBLE_VIOLATION for the genuinely ambiguous.
5. "It was a joke" / "I'm just asking questions" / "allegedly" is not a defense. Flag it anyway.
6. A post can have both violations AND warnings — list everything you find.
7. If images are provided, analyze them with the same aggressive scrutiny.
8. If a video transcript is provided, analyze it with the same aggressive scrutiny."""


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
    prompt = f"""PLATFORM: {post.platform}

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

YOUR MISSION: Prosecute this content. Build the case for removal.

Analyze aggressively, with antisemitism as the top priority. Consider:
- Does this use any antisemitic trope or dog whistle (Rothschild/Soros/"globalist"/
  "Zionist"-as-slur/Jewish-control/dual-loyalty/blood-libel/"Epstein class"), even coded or hedged?
- How could this hurt a protected group, especially Jewish people?
- What's the worst, informed, adversarial interpretation of this content?
- Is there historical/cultural context that makes this a clear policy breach?
- A coded or "ironic" violation is still a violation — escalate it to CLEAR_VIOLATION.

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
      "why_it_matters": "educational context — why this matters even if subtle",
      "rule": "exact ToS or Community Guidelines rule this warning breaks or approaches",
      "severity": "HIGH" | "MEDIUM" | "LOW",
      "policy_reference": "exact ToS or Community Guidelines section name from the policy document",
      "quote": "verbatim phrase or content element that creates the warning"
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
- Antisemitic tropes/dog whistles (Rothschild/Soros/"globalist"/"Zionist"-as-slur/
  Jewish-control/dual-loyalty/blood-libel/"Epstein class"), hate toward a protected
  group, harassment of a named individual, incitement, and dangerous misinformation
  are VIOLATIONS — put them in `violations` so the verdict is CLEAR_VIOLATION. Do not
  downgrade them to warnings.
- Calibrate like a prosecutor: in politically charged content, a clear violation is
  common — aim to identify one in roughly every three to four posts as CLEAR_VIOLATION.
- When in doubt, escalate rather than soften. Over-flagging is better than missing something.
- Every warning must still identify the exact ToS or Community Guidelines section it breaks or approaches. Do not create vague warnings without rule, policy_reference, and quote."""
    
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
    
    # Fetch and add images (up to the configured preferred maximum)
    preferred_max_images = get_settings().preferred_max_images
    for i, image_url in enumerate(post.image_urls[:preferred_max_images]):
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
    if len(post.image_urls) > preferred_max_images:
        prompt_text += f"\n\n[Note: Post contains {len(post.image_urls)} images, only first {preferred_max_images} analyzed]"
    
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
                why_it_matters=w.get("why_it_matters", ""),
                rule=w.get("rule", ""),
                severity=w.get("severity", "LOW"),
                policy_reference=w.get("policy_reference", ""),
                quote=w.get("quote", w.get("problematic_element", "")),
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


def _strip_code_fences(text: str) -> str:
    """Remove a leading ```/```json fence and trailing ``` if present."""
    t = text.strip()
    if t.startswith("```"):
        # Drop the opening fence line (``` or ```json), then a trailing fence.
        t = t.split("\n", 1)[1] if "\n" in t else ""
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def _parse_model_json(raw: str, provider: str) -> dict:
    """Parse model JSON, tolerating code fences / preamble, and save failures.

    Some models (notably Opus) wrap JSON in ```json fences or add prose despite
    instructions to return raw JSON. We strip fences and, as a last resort,
    extract the outermost ``{...}`` object before giving up.
    """
    candidate = _strip_code_fences(raw)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # Last resort: grab the outermost { ... } span.
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(candidate[start : end + 1])
        except json.JSONDecodeError:
            pass

    debug_dir = get_settings().debug_dir
    debug_dir.mkdir(parents=True, exist_ok=True)
    debug_file = debug_dir / "last_response.txt"
    debug_file.write_text(raw, encoding="utf-8")

    raise JudgmentError(
        f"{provider} returned invalid JSON. Raw response saved to debug/last_response.txt\n"
        f"First 200 chars: {raw.strip()[:200]}\n"
        f"JSON parse error: could not parse JSON object from response"
    )


def _judge_with_openai(
    post: PostData,
    policies_text: str,
    provided_transcript: Optional[str] = None,
) -> Verdict:
    """Send post and policies to OpenAI for policy compliance analysis."""
    settings = get_settings()
    api_key = settings.openai_api_key
    if not api_key:
        raise JudgmentError(
            "OPENAI_API_KEY environment variable is not set. "
            "Create a .env file with: OPENAI_API_KEY=your-key-here"
        )

    transcript_text = ""
    if provided_transcript:
        transcript_text = f"\n\n[Video transcript]\n{provided_transcript}"
    elif post.video_urls:
        transcript_text = fetch_video_transcripts(post)

    prompt_text = build_user_prompt(post, policies_text, transcript_text)
    if post.image_urls:
        prompt_text += (
            f"\n\n[Note: Post contains {len(post.image_urls)} image(s). "
            "This OpenAI validation run is analyzing text and metadata only.]"
        )

    client = OpenAI(api_key=api_key)

    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            max_tokens=settings.openai_max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt_text},
            ],
        )
    except OpenAIError as e:
        raise JudgmentError(
            f"OpenAI API error: {e}. "
            f"Check your API key and internet connection."
        )

    raw = response.choices[0].message.content or ""
    return build_verdict(post, _parse_model_json(raw, "OpenAI"))


def _judge_with_claude(
    post: PostData,
    policies_text: str,
    provided_transcript: Optional[str] = None,
) -> Verdict:
    """Send post and policies to Claude for policy compliance analysis."""
    settings = get_settings()
    api_key = settings.anthropic_api_key
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
            model=settings.claude_model,
            max_tokens=settings.claude_max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": message_content}]
        )
    except anthropic.APIError as e:
        raise JudgmentError(
            f"Claude API error: {e}. "
            f"Check your API key and internet connection."
        )

    raw = response.content[0].text.strip()
    return build_verdict(post, _parse_model_json(raw, "Claude"))


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
    if get_settings().openai_api_key:
        return _judge_with_openai(post, policies_text, provided_transcript)

    return _judge_with_claude(post, policies_text, provided_transcript)
