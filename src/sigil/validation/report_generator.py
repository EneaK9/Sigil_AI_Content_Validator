"""Enhanced second-pass report generation for CLEAR_VIOLATION posts.

The first pass (``sigil.validation.judge.judge``) decides whether a post violates policy and
returns structured violations/warnings. This module runs a *second* pass that
acts as a "prosecutor": given the post, the full platform policies, and the
first-pass findings, it produces the report-ready fields that the validator
persists for flagged posts:

  - ``category``               single primary label (e.g. "Antisemitism")
  - ``tos_cross_reference``    detailed ToS section + Community Guideline mapping
  - ``violation_explanation``  prose paragraph explaining the harm
  - ``report_text``            formal abuse report ready to submit to the platform

Provider selection mirrors ``sigil.validation.judge``: OpenAI is used when
``OPENAI_API_KEY`` is set, otherwise Claude.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import anthropic
from openai import OpenAI, OpenAIError

from sigil.config import get_settings
from sigil.validation.judge import _parse_model_json
from sigil.validation.models import JudgmentError, PostData, Verdict


REPORT_SYSTEM_PROMPT = """You are a relentless Trust & Safety PROSECUTOR. A first-pass audit \
has ALREADY established that the post below is a CLEAR violation. That finding is final and is \
NOT yours to revisit. Your one and only job is to build the most aggressive, rigorous, and \
damning submission-ready case for the post's removal.

## PROSECUTORIAL STANCE (NON-NEGOTIABLE)
- You ALWAYS assume the worst, most harmful interpretation of the content. Adversarial reading \
is mandatory.
- You NEVER defend, excuse, soften, "both-sides", contextualize away, or exonerate the post.
- You NEVER conclude the post is acceptable, "no violation", a "false positive", "legitimate \
journalism", "ordinary criticism", or that it should not be removed. Those conclusions are \
forbidden and out of scope.
- There IS a violation. Your task is to surface, name, and prove it - not to question it.
- "It's just news / business reporting / political criticism / a joke / asking questions / \
allegedly" is NOT a defense. Coded language, dog whistles, and subtext COUNT and must be \
exposed and prosecuted. Intent is irrelevant; impact and the worst reasonable reading govern.
- Surface the hateful subtext, the dog whistles, the tropes, the targeting, and the real-world \
harm even when the surface text appears neutral. Treat euphemism and "plausible deniability" \
as aggravating factors, not mitigating ones.

You are given the post (with reach metadata), the platform's full Terms of Service and \
Community Guidelines (every line prefixed with its number as "N | text"), and the first-pass \
findings.

## NON-NEGOTIABLE OUTPUT RULES
1. Return ONLY raw JSON. No markdown fences, no preamble. First character '{', last '}'.
2. Cite EXACT line numbers from the numbered policy text for every policy quote, e.g. \
"Community Guidelines, 'Hate Speech', line 16". Quote policy text VERBATIM. Never invent or \
paraphrase policy text, and never cite a line number that is not present.
3. Be EXHAUSTIVE. Identify every distinct policy category the post breaches (hate speech, \
violent/criminal behavior, harassment, misinformation, dangerous orgs, etc.) - not just the \
most obvious one. Map each violating element of the post to ALL sections it breaches. Charge \
everything that can plausibly be charged.
4. Explain the incorporation chain: how the Terms of Service bind the user to the Community \
Guidelines (cite the specific ToS section + line), so a guideline breach is also a ToS breach.
5. Write at the length and depth of a professional legal complaint. Terse output is a failure. \
Each field below must be thorough and self-contained.
6. Every field MUST be FINAL and submission-ready. NEVER emit placeholder / fill-in-the-blank \
tokens of ANY kind - no square-bracket placeholders ('[Reporter]', '[Your Name]', \
'[Current Date]', '[Date]', '[Position]'), no 'FROM:'/'DATE:' header lines, and no blank \
signature. Use ONLY the concrete facts provided (post URL, author, posted date, reach). Do \
NOT invent a reporter identity or a date. Any closing must be a neutral generic one (e.g. \
"Submitted for Trust & Safety review") with no name or bracketed field.

## FIELD REQUIREMENTS
- category: single primary violation label (e.g. 'Antisemitism', 'Hate Speech', 'Harassment').
- tos_cross_reference: for EACH violation category, a block of the form \
"[Category] ToS Section X ('Title', line N) prohibits '<verbatim quote>' ... and incorporates \
the Community Guidelines (line N) - the post breaches '<Guideline path>' (line N): '<verbatim quote>'". \
Separate categories with '; '. Quote real, line-numbered policy text only.
- violation_explanation: a thorough multi-sentence prosecutorial analysis of WHAT is wrong, \
the specific tropes/dog-whistles/mechanisms at work, the concrete harm and who it targets, and \
WHY it unambiguously violates policy under the worst reasonable reading. Reference the post's \
own words. Do NOT hedge and do NOT argue any point in the post's favor.
- report_text: a complete, FINAL formal abuse report to the platform's Trust & Safety team, \
ready to submit with zero placeholders: a title/subject; post details (URL, author, posted \
date, and reach as "Reach: N views, N likes, N comments" from the metadata); a numbered \
section per violation category citing the verbatim Community Guideline AND Terms of Service \
text WITH line numbers; and a closing demand for removal and account review. No \
'FROM:'/'DATE:' block or blank signature.

## OUTPUT SCHEMA
{
  "category": "string",
  "tos_cross_reference": "string",
  "violation_explanation": "string",
  "report_text": "string"
}"""


@dataclass
class ViolationReport:
    """Report-ready fields produced by the second-pass prosecutor."""
    category: str
    tos_cross_reference: str
    violation_explanation: str
    report_text: str


def _summarize_findings(verdict: Verdict) -> str:
    """Render the first-pass violations + warnings into a compact text block."""
    lines: list[str] = []

    if verdict.violations:
        lines.append("VIOLATIONS FOUND (first pass):")
        for i, v in enumerate(verdict.violations, 1):
            lines.append(
                f"{i}. rule={v.rule} | severity={v.severity} | "
                f"policy_reference={v.policy_reference}"
            )
            lines.append(f"   quote: {v.quote}")
            lines.append(f"   explanation: {v.explanation}")

    if verdict.warnings:
        lines.append("")
        lines.append("ADDITIONAL WARNINGS (first pass):")
        for i, w in enumerate(verdict.warnings, 1):
            affected = ", ".join(w.affected_groups) if w.affected_groups else "N/A"
            lines.append(
                f"{i}. category={w.category} | risk_level={w.risk_level} | "
                f"severity={w.severity} | rule={w.rule} | "
                f"policy_reference={w.policy_reference}"
            )
            lines.append(f"   element: {w.quote or w.problematic_element}")
            lines.append(f"   explanation: {w.explanation}")
            lines.append(f"   affected_groups: {affected}")

    return "\n".join(lines)


def _format_metadata(metadata: dict | None) -> str:
    """Render post reach/metadata for the report prompt (best-effort)."""
    if not metadata:
        return "POST METADATA: (not available)"
    posted_at = metadata.get("posted_at")
    hashtags = metadata.get("hashtags") or []
    if isinstance(hashtags, (list, tuple)):
        hashtags = ", ".join(str(h) for h in hashtags)
    parts = [
        f"POSTED AT: {posted_at}" if posted_at else None,
        f"VIEWS: {metadata.get('view_count')}"
        if metadata.get("view_count") is not None
        else None,
        f"LIKES: {metadata.get('like_count')}"
        if metadata.get("like_count") is not None
        else None,
        f"COMMENTS: {metadata.get('comment_count')}"
        if metadata.get("comment_count") is not None
        else None,
        f"SHARES: {metadata.get('share_count')}"
        if metadata.get("share_count") is not None
        else None,
        f"HASHTAGS: {hashtags}" if hashtags else None,
    ]
    return "POST METADATA:\n" + "\n".join(p for p in parts if p)


# Detects fill-in-the-blank placeholders like [Reporter], [Current Date], [Your Name].
_PLACEHOLDER_RE = re.compile(r"\[[^\]\n]{1,40}\]")

_PLACEHOLDER_CORRECTION = (
    "\n\nIMPORTANT CORRECTION: A previous draft contained fill-in-the-blank "
    "placeholders. Reproduce ALL fields as FINAL, submission-ready text with NO "
    "bracketed placeholders (no '[Reporter]', '[Current Date]', '[Your Name]', "
    "etc.), NO 'FROM:'/'DATE:' header lines, and NO blank signature. Use only the "
    "concrete facts provided."
)


def _has_placeholders(report: "ViolationReport") -> bool:
    """True if any report field still contains a fill-in placeholder."""
    for value in (
        report.category,
        report.tos_cross_reference,
        report.violation_explanation,
        report.report_text,
    ):
        if _PLACEHOLDER_RE.search(value or ""):
            return True
    return False


def _build_report_prompt(
    post: PostData,
    policies_text: str,
    verdict: Verdict,
    metadata: dict | None = None,
    extra_instruction: str = "",
) -> str:
    """Build the user prompt for the second-pass report generation."""
    findings = _summarize_findings(verdict)
    return extra_instruction + f"""PLATFORM: {post.platform}

POST URL: {post.url}
POST AUTHOR: {post.author}
POST TITLE: {post.title}
{_format_metadata(metadata)}
POST TEXT:
---
{post.text}
---

FIRST-PASS FINDINGS (already established as a CLEAR violation — prosecute, do not revisit):
---
{findings}
---

PLATFORM POLICIES (Community Guidelines + Terms of Service; each line is prefixed \
with its line number as "N | text" - cite these exact line numbers):
---
{policies_text}
---

Build the formal case. Return the JSON object described in the system prompt, \
cross-referencing the exact line-numbered policy sections quoted above."""


def _build_report(data: dict) -> ViolationReport:
    """Convert parsed model JSON into a ViolationReport."""
    return ViolationReport(
        category=str(data.get("category", "") or ""),
        tos_cross_reference=str(data.get("tos_cross_reference", "") or ""),
        violation_explanation=str(data.get("violation_explanation", "") or ""),
        report_text=str(data.get("report_text", "") or ""),
    )


def _generate_with_openai(
    post: PostData,
    policies_text: str,
    verdict: Verdict,
    metadata: dict | None = None,
    extra_instruction: str = "",
) -> ViolationReport:
    settings = get_settings()
    api_key = settings.openai_api_key
    if not api_key:
        raise JudgmentError(
            "OPENAI_API_KEY environment variable is not set. "
            "Create a .env file with: OPENAI_API_KEY=your-key-here"
        )

    prompt_text = _build_report_prompt(
        post, policies_text, verdict, metadata, extra_instruction
    )
    client = OpenAI(api_key=api_key)

    try:
        response = client.chat.completions.create(
            model=settings.report_openai_model,
            max_tokens=settings.report_max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": REPORT_SYSTEM_PROMPT},
                {"role": "user", "content": prompt_text},
            ],
        )
    except OpenAIError as e:
        raise JudgmentError(
            f"OpenAI API error during report generation: {e}. "
            f"Check your API key and internet connection."
        )

    raw = response.choices[0].message.content or ""
    return _build_report(_parse_model_json(raw, "OpenAI"))


def _generate_with_claude(
    post: PostData,
    policies_text: str,
    verdict: Verdict,
    metadata: dict | None = None,
    extra_instruction: str = "",
) -> ViolationReport:
    settings = get_settings()
    api_key = settings.anthropic_api_key
    if not api_key:
        raise JudgmentError(
            "ANTHROPIC_API_KEY environment variable is not set. "
            "Create a .env file with: ANTHROPIC_API_KEY=your-key-here"
        )

    prompt_text = _build_report_prompt(
        post, policies_text, verdict, metadata, extra_instruction
    )
    client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.messages.create(
            model=settings.report_claude_model,
            max_tokens=settings.report_max_tokens,
            system=REPORT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt_text}],
        )
    except anthropic.APIError as e:
        raise JudgmentError(
            f"Claude API error during report generation: {e}. "
            f"Check your API key and internet connection."
        )

    raw = response.content[0].text.strip()
    return _build_report(_parse_model_json(raw, "Claude"))


def generate_violation_report(
    post: PostData,
    policies_text: str,
    verdict: Verdict,
    metadata: dict | None = None,
) -> ViolationReport:
    """Run the second-pass prosecutor to produce report-ready fields.

    This pass runs ONLY on CLEAR_VIOLATION posts, so it uses the premium
    ``report_*`` model + token budget (see ``Settings``). By default it prefers
    Anthropic (Claude Opus) when an Anthropic key is present, so the expensive
    model is reserved for flagged rows while the first-pass judge stays cheap.

    Args:
        post: The post that was judged CLEAR_VIOLATION.
        policies_text: Platform policy markdown (line-numbered for citations).
        verdict: The first-pass Verdict (its violations/warnings inform the report).
        metadata: Optional post reach/metadata (views, likes, comments, posted_at,
            hashtags) included in the prompt so the report can cite real reach.

    Returns:
        ViolationReport with category, tos_cross_reference, violation_explanation,
        and report_text.

    Raises:
        JudgmentError: If the model call fails or returns invalid JSON.
    """
    settings = get_settings()
    # Premium model lives on Anthropic (Opus); prefer it for the report pass.
    if settings.report_prefer_anthropic and settings.anthropic_api_key:
        generate = _generate_with_claude
    elif settings.openai_api_key:
        generate = _generate_with_openai
    elif settings.anthropic_api_key:
        generate = _generate_with_claude
    else:
        raise JudgmentError(
            "No LLM API key configured for report generation. Set ANTHROPIC_API_KEY "
            "(recommended for the report pass) or OPENAI_API_KEY."
        )

    report = generate(post, policies_text, verdict, metadata)
    # Guarantee final, submission-ready cells: if any fill-in placeholder slipped
    # through, regenerate once with an explicit correction.
    if _has_placeholders(report):
        report = generate(
            post, policies_text, verdict, metadata, _PLACEHOLDER_CORRECTION
        )
    return report
