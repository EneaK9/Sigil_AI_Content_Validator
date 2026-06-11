# PolicyGuard Output Format

## Verdict Types

- `PASS` — Completely clean content (should be rare)
- `POSSIBLE_VIOLATION` — Found issues but not clear policy violations
- `CLEAR_VIOLATION` — Definite policy violation

---

## Example 1: POSSIBLE_VIOLATION (found problematic content)

```json
{
  "verdict": "POSSIBLE_VIOLATION",
  "platform": "facebook",
  "post_url": "https://facebook.com/post/123",
  "post_text": "Wow, your English is so good! Where did you learn it?",
  "violations": [],
  "warnings": [
    {
      "category": "Racism / Microaggression",
      "risk_level": "OBVIOUS",
      "explanation": "This comment assumes the person is not a native English speaker based on their appearance or name. It implies they are foreign or 'other' even if they were born in an English-speaking country. This is a textbook microaggression.",
      "problematic_element": "Wow, your English is so good! Where did you learn it?",
      "affected_groups": ["immigrants", "people of color", "anyone perceived as foreign"],
      "why_it_matters": "Perpetual foreigner stereotype causes real psychological harm. Being constantly reminded you're seen as 'other' in your own home creates alienation and distress."
    }
  ],
  "passed_checks": ["Violence", "Adult Content", "Spam"],
  "confidence": 0.85,
  "recommendation": "",
  "checked_at": "2026-06-11T12:15:30Z",
  "report_message": "Subject: Content Review Request - Potential Policy Concern on Facebook\n\nTo: Facebook Trust & Safety Team\n\nI am flagging content for your review that may approach your Community Guidelines thresholds.\n\nPOST DETAILS:\n- URL: https://facebook.com/post/123\n- Date Analyzed: 2026-06-11T12:15:30Z\n\nASSESSMENT:\nThis content does not clearly violate your stated policies, but contains elements that warrant review. Confidence: 85%.\n\nIDENTIFIED CONCERNS:\n\n1. Racism / Microaggression\n   Risk Level: OBVIOUS\n\n   Problematic Element: \"Wow, your English is so good! Where did you learn it?\"\n\n   Analysis: This comment assumes the person is not a native English speaker based on their appearance or name. It implies they are foreign or 'other' even if they were born in an English-speaking country. This is a textbook microaggression.\n\n   Potentially Affected Groups: immigrants, people of color, anyone perceived as foreign\n\n   Why This Matters: Perpetual foreigner stereotype causes real psychological harm. Being constantly reminded you're seen as 'other' in your own home creates alienation and distress.\n\n---\n\nCONTEXT:\nWhile this content may not meet the threshold for removal under current policies, we believe it contributes to a hostile environment for the communities identified above. We request your team review whether:\n\n1. The content crosses policy lines under closer examination\n2. The account shows a pattern of similar borderline content\n3. Updated policy guidance should address this type of content\n\nThis report is submitted in good faith to support platform safety.\n\nRegards,\nSigil AI Content Validator"
}
```

---

## Example 2: POSSIBLE_VIOLATION (cultural appropriation)

```json
{
  "verdict": "POSSIBLE_VIOLATION",
  "platform": "instagram",
  "post_url": "https://instagram.com/p/abc123",
  "post_text": "Love starting my day with some yoga and chai tea 🧘‍♀️✨ #blessed #mindfulness",
  "violations": [],
  "warnings": [
    {
      "category": "Cultural Appropriation",
      "risk_level": "INTERPRETIVE",
      "explanation": "Post commodifies and westernizes yoga (a sacred Hindu practice) as a wellness trend without acknowledgment of its origins. 'Chai tea' is redundant (chai means tea) showing superficial engagement with the culture. Combined with #blessed, this treats South Asian spiritual practices as aesthetic lifestyle accessories.",
      "problematic_element": "yoga and chai tea 🧘‍♀️✨ #blessed #mindfulness",
      "affected_groups": ["South Asian communities", "Hindu practitioners", "Indian diaspora"],
      "why_it_matters": "The commercialization of sacred practices divorces them from their spiritual and cultural context, while the communities they come from often face discrimination for those same practices."
    }
  ],
  "passed_checks": ["Violence", "Hate Speech", "Adult Content"],
  "confidence": 0.78,
  "recommendation": "",
  "checked_at": "2026-06-11T12:16:00Z"
}
```

---

## Example 3: POSSIBLE_VIOLATION (antisemitism dog whistle)

```json
{
  "verdict": "POSSIBLE_VIOLATION",
  "platform": "x",
  "post_url": "https://x.com/user/status/123456",
  "post_text": "Funny how the same small group of elites controls the banks, media, and politics. Open your eyes, people. Follow the money.",
  "violations": [],
  "warnings": [
    {
      "category": "Antisemitism / Conspiracy Theory",
      "risk_level": "OBVIOUS",
      "explanation": "This post uses classic antisemitic conspiracy tropes: 'small group of elites', control of banks/media/politics, 'follow the money'. These are well-documented dog whistles that have been used to target Jewish communities for centuries. Even without explicitly naming Jewish people, the framing is unmistakable.",
      "problematic_element": "same small group of elites controls the banks, media, and politics",
      "affected_groups": ["Jewish communities"],
      "why_it_matters": "These conspiracy theories have directly led to violence against Jewish people throughout history, from pogroms to the Holocaust to modern hate crimes. They must be identified and flagged regardless of whether they explicitly name Jews."
    }
  ],
  "passed_checks": ["Violence", "Adult Content"],
  "confidence": 0.92,
  "recommendation": "",
  "checked_at": "2026-06-11T12:17:00Z"
}
```

---

## Example 4: CLEAR_VIOLATION (with additional warnings)

```json
{
  "verdict": "CLEAR_VIOLATION",
  "platform": "reddit",
  "post_url": "https://reddit.com/r/example/comments/xyz",
  "post_text": "[content with slur and other issues]",
  "violations": [
    {
      "rule": "Hate Speech",
      "severity": "HIGH",
      "explanation": "Post contains a direct slur targeting an ethnic group.",
      "policy_reference": "Reddit Content Policy - Rule 1: Hateful content",
      "quote": "[the exact slur]"
    }
  ],
  "warnings": [
    {
      "category": "Sexism",
      "risk_level": "OBVIOUS",
      "explanation": "In addition to the slur, the post also contains sexist commentary about women's capabilities in leadership roles.",
      "problematic_element": "[the sexist phrase]",
      "affected_groups": ["women"],
      "why_it_matters": "Sexist stereotypes about women in leadership perpetuate workplace discrimination and glass ceiling effects."
    },
    {
      "category": "Ableism",
      "risk_level": "INTERPRETIVE",
      "explanation": "Uses 'crazy' as a pejorative to dismiss opposing viewpoints.",
      "problematic_element": "that's crazy",
      "affected_groups": ["people with mental illness"],
      "why_it_matters": "Casual use of mental health terms as insults stigmatizes mental illness and trivializes the experiences of those who suffer from it."
    }
  ],
  "passed_checks": ["Spam", "Adult Content"],
  "confidence": 0.96,
  "recommendation": "Remove post. Flag all identified issues in moderation log.",
  "checked_at": "2026-06-11T12:18:00Z"
}
```

---

## Example 5: PASS (rare — genuinely clean)

```json
{
  "verdict": "PASS",
  "platform": "tiktok",
  "post_url": "https://tiktok.com/@user/video/123",
  "post_text": "Here's my cat sleeping on the couch.",
  "violations": [],
  "warnings": [],
  "passed_checks": ["Violence", "Hate Speech", "Adult Content", "Harassment", "Misinformation", "Spam"],
  "confidence": 0.95,
  "recommendation": "",
  "checked_at": "2026-06-11T12:19:00Z"
}
```

---

## Field Reference

| Field | Description |
|-------|-------------|
| `verdict` | `PASS`, `POSSIBLE_VIOLATION`, or `CLEAR_VIOLATION` |
| `violations[]` | Clear policy violations (only for `CLEAR_VIOLATION`) |
| `warnings[]` | Possible issues flagged (for `POSSIBLE_VIOLATION` or alongside violations) |
| `warnings[].category` | Type: racism, sexism, antisemitism, microaggression, etc. |
| `warnings[].risk_level` | `OBVIOUS`, `INTERPRETIVE`, or `DEEP_READ` |
| `warnings[].affected_groups` | Who could be harmed |
| `warnings[].why_it_matters` | Educational context |
| `confidence` | 0.0 to 1.0 |
| `report_message` | **Auto-generated** full report message ready to send to platform (empty if PASS) |

---

## Platform Report Message

After analysis, generate a formal report message to submit to the platform's moderation team.

### For CLEAR_VIOLATION:

```
Subject: Content Violation Report - [Platform] Community Guidelines

To: [Platform] Trust & Safety Team

I am reporting a violation of [Platform]'s Community Guidelines.

POST DETAILS:
- URL: [post_url]
- Author: [author]
- Date Analyzed: [checked_at]

VIOLATION SUMMARY:
This content violates your platform's policies with [confidence]% confidence.

SPECIFIC VIOLATIONS:

1. [violation.rule] (Severity: [violation.severity])
   Policy Reference: [violation.policy_reference]
   
   Problematic Content: "[violation.quote]"
   
   Explanation: [violation.explanation]

[Repeat for each violation]

ADDITIONAL CONCERNS:

[For each warning:]
- [warning.category] ([warning.risk_level])
  Element: "[warning.problematic_element]"
  Impact: [warning.explanation]
  Affected Communities: [warning.affected_groups]

RECOMMENDATION:
[recommendation]

This report was generated by automated content analysis. Please review and take appropriate action under your platform's enforcement policies.

Regards,
[Sender/Organization]
```

---

### For POSSIBLE_VIOLATION:

```
Subject: Content Review Request - Potential Policy Concern on [Platform]

To: [Platform] Trust & Safety Team

I am flagging content for your review that may approach your Community Guidelines thresholds.

POST DETAILS:
- URL: [post_url]
- Author: [author]
- Date Analyzed: [checked_at]

ASSESSMENT:
This content does not clearly violate your stated policies, but contains elements that warrant review. Confidence: [confidence]%.

IDENTIFIED CONCERNS:

[For each warning:]

[i]. [warning.category]
    Risk Level: [warning.risk_level]
    
    Problematic Element: "[warning.problematic_element]"
    
    Analysis: [warning.explanation]
    
    Potentially Affected Groups: [warning.affected_groups]
    
    Why This Matters: [warning.why_it_matters]

---

CONTEXT:
While this content may not meet the threshold for removal under current policies, we believe it contributes to a hostile environment for the communities identified above. We request your team review whether:

1. The content crosses policy lines under closer examination
2. The account shows a pattern of similar borderline content
3. Updated policy guidance should address this type of content

This report is submitted in good faith to support platform safety.

Regards,
[Sender/Organization]
```

---

### Example: Full Report for Antisemitism Case

```
Subject: Content Review Request - Potential Antisemitic Content on X

To: X Trust & Safety Team

I am flagging content for your review that may approach your Community Guidelines thresholds.

POST DETAILS:
- URL: https://x.com/user/status/123456
- Author: @username
- Date Analyzed: 2026-06-11T12:17:00Z

ASSESSMENT:
This content does not clearly violate your stated policies, but contains elements that warrant review. Confidence: 92%.

IDENTIFIED CONCERNS:

1. Antisemitism / Conspiracy Theory
   Risk Level: OBVIOUS
   
   Problematic Element: "same small group of elites controls the banks, media, and politics"
   
   Analysis: This post uses classic antisemitic conspiracy tropes: 'small group of elites', control of banks/media/politics, 'follow the money'. These are well-documented dog whistles that have been used to target Jewish communities for centuries. Even without explicitly naming Jewish people, the framing is unmistakable.
   
   Potentially Affected Groups: Jewish communities
   
   Why This Matters: These conspiracy theories have directly led to violence against Jewish people throughout history, from pogroms to the Holocaust to modern hate crimes. They must be identified and flagged regardless of whether they explicitly name Jews.

---

CONTEXT:
While this content may not meet the threshold for removal under current policies, we believe it contributes to a hostile environment for the communities identified above. We request your team review whether:

1. The content crosses policy lines under closer examination
2. The account shows a pattern of similar borderline content
3. Updated policy guidance should address this type of content

This report is submitted in good faith to support platform safety.

Regards,
Sigil AI Content Validator
```

---

### Example: Full Report for Clear Violation

```
Subject: Content Violation Report - Reddit Community Guidelines

To: Reddit Trust & Safety Team

I am reporting a violation of Reddit's Community Guidelines.

POST DETAILS:
- URL: https://reddit.com/r/example/comments/xyz
- Author: u/username
- Date Analyzed: 2026-06-11T12:18:00Z

VIOLATION SUMMARY:
This content violates your platform's policies with 96% confidence.

SPECIFIC VIOLATIONS:

1. Hate Speech (Severity: HIGH)
   Policy Reference: Reddit Content Policy - Rule 1: Hateful content
   
   Problematic Content: "[the exact slur]"
   
   Explanation: Post contains a direct slur targeting an ethnic group.

ADDITIONAL CONCERNS:

- Sexism (OBVIOUS)
  Element: "[the sexist phrase]"
  Impact: In addition to the slur, the post also contains sexist commentary about women's capabilities in leadership roles.
  Affected Communities: women

- Ableism (INTERPRETIVE)
  Element: "that's crazy"
  Impact: Uses 'crazy' as a pejorative to dismiss opposing viewpoints.
  Affected Communities: people with mental illness

RECOMMENDATION:
Remove post. Flag all identified issues in moderation log.

This report was generated by automated content analysis. Please review and take appropriate action under your platform's enforcement policies.

Regards,
Sigil AI Content Validator
```
