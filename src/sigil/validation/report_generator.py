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

from dataclasses import dataclass

import anthropic
from openai import OpenAI, OpenAIError

from sigil.config import get_settings
from sigil.validation.judge import _parse_model_json
from sigil.validation.models import JudgmentError, PostData, Verdict


REPORT_SYSTEM_PROMPT = """You are a content-policy prosecutor. A first-pass audit has \
already determined that the post below is a CLEAR violation of the platform's policies. \
Your job is to build the formal case for removal.

You are given the post, the platform's full Terms of Service and Community Guidelines, \
and the specific violations already found. Produce a rigorous, citation-backed report.

## RULES
1. Return ONLY raw JSON. No markdown fences, no preamble. The first character must be \
'{' and the last must be '}'.
2. Ground every claim in the provided policy text. Quote exact ToS sections and \
Community Guideline lines. Never invent policy text that is not present.
3. Cross-reference how the Terms of Service incorporate the Community Guidelines, and \
map each violating element of the post to the specific section(s) it breaches.
4. Be precise, formal, and damning. This report will be submitted to the platform's \
Trust & Safety team.

## OUTPUT SCHEMA
{
  "category": "single primary violation label, e.g. 'Antisemitism', 'Hate Speech', 'Harassment'",
  "tos_cross_reference": "detailed cross-reference mapping each violation to exact ToS sections AND the Community Guidelines they incorporate; quote the policy text verbatim; separate multiple violations with '; '",
  "violation_explanation": "a thorough prose paragraph explaining what is wrong with the content, the harm it causes, and why it clearly violates policy",
  "report_text": "a complete formal abuse report addressed to the platform's Trust & Safety team, including post details, each violation with its quoted policy references, and a request for removal"
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


def _build_report_prompt(
    post: PostData, policies_text: str, verdict: Verdict
) -> str:
    """Build the user prompt for the second-pass report generation."""
    findings = _summarize_findings(verdict)
    return f"""PLATFORM: {post.platform}

POST URL: {post.url}
POST AUTHOR: {post.author}
POST TITLE: {post.title}
POST TEXT:
---
{post.text}
---

FIRST-PASS FINDINGS (already confirmed as a CLEAR violation):
---
{findings}
---

PLATFORM POLICIES (Community Guidelines + Terms of Service):
---
{policies_text}
---

Build the formal case. Return the JSON object described in the system prompt, \
cross-referencing the exact policy sections quoted above."""


def _build_report(data: dict) -> ViolationReport:
    """Convert parsed model JSON into a ViolationReport."""
    return ViolationReport(
        category=str(data.get("category", "") or ""),
        tos_cross_reference=str(data.get("tos_cross_reference", "") or ""),
        violation_explanation=str(data.get("violation_explanation", "") or ""),
        report_text=str(data.get("report_text", "") or ""),
    )


def _generate_with_openai(
    post: PostData, policies_text: str, verdict: Verdict
) -> ViolationReport:
    settings = get_settings()
    api_key = settings.openai_api_key
    if not api_key:
        raise JudgmentError(
            "OPENAI_API_KEY environment variable is not set. "
            "Create a .env file with: OPENAI_API_KEY=your-key-here"
        )

    prompt_text = _build_report_prompt(post, policies_text, verdict)
    client = OpenAI(api_key=api_key)

    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            max_tokens=settings.openai_max_tokens,
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
    post: PostData, policies_text: str, verdict: Verdict
) -> ViolationReport:
    settings = get_settings()
    api_key = settings.anthropic_api_key
    if not api_key:
        raise JudgmentError(
            "ANTHROPIC_API_KEY environment variable is not set. "
            "Create a .env file with: ANTHROPIC_API_KEY=your-key-here"
        )

    prompt_text = _build_report_prompt(post, policies_text, verdict)
    client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=settings.claude_max_tokens,
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
) -> ViolationReport:
    """Run the second-pass prosecutor to produce report-ready fields.

    Args:
        post: The post that was judged CLEAR_VIOLATION.
        policies_text: Concatenated platform policy markdown.
        verdict: The first-pass Verdict (its violations/warnings inform the report).

    Returns:
        ViolationReport with category, tos_cross_reference, violation_explanation,
        and report_text.

    Raises:
        JudgmentError: If the model call fails or returns invalid JSON.
    """
    if get_settings().openai_api_key:
        return _generate_with_openai(post, policies_text, verdict)
    return _generate_with_claude(post, policies_text, verdict)
